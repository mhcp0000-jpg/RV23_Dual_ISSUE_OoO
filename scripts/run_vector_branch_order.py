"""Observe speculative vectors behind delayed scalar branches and their squash."""
import argparse
import json
import re
import subprocess

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/vector_branch_order'
SOURCE = 'sw/tests/rv64_vector_branch_order.S'
TOP = 'rv23_vector_branch_order_tb'


def wrong_pcs():
    text = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n',
                                    str(FOLDER / 'test.elf')], text=True)
    symbols = {name: int(address, 16) for address, name in
               re.findall(r'^([\da-f]+) \w (wrong\d+)$', text, re.M)}
    assert set(symbols) == {f'wrong{i}' for i in range(6)}
    return symbols


def verify_traces(sail_trace, rtl_trace):
    rows = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), rows)
    assert mismatch is None, mismatch
    pcs = set(wrong_pcs().values())
    branches = []
    for row in rows:
        pc = int(row['pc'], 16)
        assert pc not in pcs, row
        if pc >= 0x80000000:
            assert row['trap'] == '0', row
        if pc + 4 in pcs:
            assert int(row['instruction'], 16) & 0x7f == 0x63, row
            branches.append(pc)
    assert len(branches) == 6 and len(set(branches)) == 6
    return dict(cases=6, matched_events=events)


def verify_pipeline(log):
    match = re.search(r'^VECTOR BRANCH ORDER dispatched=([\da-f]+) recovered=([\da-f]+)$', log, re.M)
    assert match and tuple(int(value, 16) for value in match.groups()) == (63, 63)
    assert 'PASS rv32_program_tb' in log and '[host-finish code=0]' in log
    return dict(speculative_vectors=6, recovered_cases=6)


def check():
    record = json.loads((FOLDER / 'report.json').read_text(encoding='utf-8'))
    assert record['passed'] and record['generator_sha256'] == sha(__file__)
    for model in (record['model'], record['pipeline_model']):
        assert source_inputs(model['inputs']) == model['inputs']
        assert sha(ROOT / model['binary']) == model['binary_sha256']
        for phase in ('compile', 'build'):
            step = model[phase]
            assert step['passed'] and step['exit_code'] == 0
            assert sha(ROOT / step['log']) == step['log_sha256']
    assert source_inputs(record['runtime_inputs']) == record['runtime_inputs']
    for filename, key in [('test.elf', 'elf_sha256'), ('commit.csv', 'trace_sha256'),
                          ('sail.csv', 'sail_trace_sha256'),
                          ('pipeline_commit.csv', 'pipeline_trace_sha256')]:
        assert sha(FOLDER / filename) == record[key]
    for key in ('compile', 'run', 'sail', 'pipeline_run'):
        step = record[key]
        assert step['passed'] and step['exit_code'] == 0
        assert sha(ROOT / step['log']) == step['log_sha256']
    assert record['outcomes'] == verify_traces(FOLDER / 'sail.csv', FOLDER / 'commit.csv')
    assert record['outcomes'] == verify_traces(FOLDER / 'sail.csv', FOLDER / 'pipeline_commit.csv')
    log = (ROOT / record['pipeline_run']['log']).read_text(encoding='utf-8')
    assert record['pipeline'] == verify_pipeline(log)
    broken = log.replace('dispatched=3f', 'dispatched=1f')
    assert broken != log
    try:
        verify_pipeline(broken)
    except AssertionError:
        pass
    else:
        raise AssertionError('Missing speculative vector witness accepted')
    return record['outcomes'], record['pipeline']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not args.check:
        run_fixture(ROOT / SOURCE, FOLDER, __file__, verify_traces)
        record = json.loads((FOLDER / 'report.json').read_bytes())
        record['passed'] = False
        dump(FOLDER / 'report.json', record)
        files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
            'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
            'tb/rv32_program_tb.sv', f'tb/{TOP}.sv', 'tb/e2e/dpi/elf_loader.cpp']
        model_path = FOLDER / 'pipeline_model.json'
        model = json.loads(model_path.read_bytes()) if model_path.exists() else None
        with Simulator() as sim:
            if not model or model['inputs'] != source_inputs(files) or sha(ROOT / model['binary']) != model['binary_sha256']:
                model = sim.build('rv23_vector_branch_order', TOP, files)
                dump(model_path, model)
            trace = FOLDER / 'pipeline_commit.csv'
            run, log = sim.run([ROOT / model['binary'], f'+elf={(FOLDER / "test.elf").relative_to(ROOT).as_posix()}',
                f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+htif', '+quiet_commit',
                '+timeout_cycles=100000', '+expected_exit_code=0',
                *[f'+{name}={pc:x}' for name, pc in wrong_pcs().items()]], FOLDER / 'pipeline.log', 120)
        record.update(passed=True, pipeline_model=model, pipeline_run=run,
                      pipeline=verify_pipeline(log), pipeline_trace_sha256=sha(trace))
        dump(FOLDER / 'report.json', record)
    print('PASS scalar branch recovery protects vector state and memory', *check())


if __name__ == '__main__':
    main()

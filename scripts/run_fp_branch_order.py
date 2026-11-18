"""Observe completed and in-flight wrong-path FP work, recovery and no effects."""
import argparse
import json
import re
import subprocess

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/fp_branch_order'
SOURCE = 'sw/tests/rv64_fp_branch_order.S'
TOP = 'rv23_fp_branch_order_tb'


def wrong_pcs():
    text = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(FOLDER / 'test.elf')], text=True)
    result = {name: int(address, 16) for address, name in
        re.findall(r'^([\da-f]+) \w (wrong(?:_begin|_end)?[0-7])$', text, re.M)}
    assert len(result) == 24
    return result


def verify_traces(sail_trace, rtl_trace):
    actual = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), actual)
    assert mismatch is None, mismatch
    symbols = wrong_pcs()
    ranges = [(symbols[f'wrong_begin{i}'], symbols[f'wrong_end{i}']) for i in range(8)]
    for row in actual:
        pc = int(row['pc'], 16)
        assert not any(start <= pc < end for start, end in ranges), row
        if pc >= 0x80000000:
            assert row['trap'] == '0', row
    return dict(cases=8, matched_events=events)


def verify_pipeline(log):
    match = re.search(r'^FP BRANCH ORDER dispatched=([\da-f]+) accepted=([\da-f]+) completed=([\da-f]+) recovered=([\da-f]+) slow_killed=(\d+)$', log, re.M)
    assert match
    dispatched, accepted, completed, recovered, killed = (int(value, 16) for value in match.groups())
    assert (dispatched, accepted, recovered, killed) == (255, 79, 255, 1)
    assert completed & 15 == 15 and not completed & 64
    assert 'PASS rv32_program_tb' in log and '[host-finish code=0]' in log
    return dict(dispatched_cases=8, accepted_fp_cases=5, completed_wrong_fp_cases=completed.bit_count(),
                recovered_cases=8, in_flight_slow_kills=1)


def check():
    report = json.loads((FOLDER / 'report.json').read_bytes())
    assert report['passed'] and report['generator_sha256'] == sha(__file__)
    for model in (report['model'], report['pipeline_model']):
        assert source_inputs(model['inputs']) == model['inputs']
        assert sha(ROOT / model['binary']) == model['binary_sha256']
        for phase in ('compile', 'build'):
            step = model[phase]
            assert step['passed'] and step['exit_code'] == 0 and sha(ROOT / step['log']) == step['log_sha256']
    assert {p: h for p, h in report['model']['inputs'].items() if p.startswith('rtl/')} == {
        p: h for p, h in report['pipeline_model']['inputs'].items() if p.startswith('rtl/')}
    assert source_inputs(report['runtime_inputs']) == report['runtime_inputs']
    for filename, key in [('test.elf', 'elf_sha256'), ('commit.csv', 'trace_sha256'),
                          ('sail.csv', 'sail_trace_sha256'), ('pipeline_commit.csv', 'pipeline_trace_sha256')]:
        assert sha(FOLDER / filename) == report[key]
    for key in ('compile', 'run', 'sail', 'pipeline_run'):
        step = report[key]
        assert step['passed'] and step['exit_code'] == 0 and sha(ROOT / step['log']) == step['log_sha256']
    assert report['outcomes'] == verify_traces(FOLDER / 'sail.csv', FOLDER / 'commit.csv')
    assert report['outcomes'] == verify_traces(FOLDER / 'sail.csv', FOLDER / 'pipeline_commit.csv')
    log = (ROOT / report['pipeline_run']['log']).read_text(encoding='utf-8')
    assert report['pipeline'] == verify_pipeline(log)
    controls = []
    for original, wrong in [('accepted=4f', 'accepted=0f'), ('recovered=ff', 'recovered=7f'), ('slow_killed=1', 'slow_killed=0')]:
        broken = log.replace(original, wrong)
        assert broken != log
        try:
            verify_pipeline(broken)
        except AssertionError:
            controls.append(original)
        else:
            raise AssertionError('Missing FP pipeline witness accepted')
    return report['outcomes'], report['pipeline'], controls


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not args.check:
        run_fixture(ROOT / SOURCE, FOLDER, __file__, verify_traces, timeout_cycles=200000)
        report = json.loads((FOLDER / 'report.json').read_bytes())
        report.update(passed=False, complete_profile_validation=False,
            scope='Finite scalar FP wrong-path result/flag/memory suppression and slow owner kill; not full FS/guest or scheduling proof')
        dump(FOLDER / 'report.json', report)
        files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
            'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
            'tb/rv32_program_tb.sv', f'tb/{TOP}.sv', 'tb/e2e/dpi/elf_loader.cpp']
        model_path = FOLDER / 'pipeline_model.json'
        model = json.loads(model_path.read_bytes()) if model_path.exists() else None
        with Simulator() as sim:
            if not model or model['inputs'] != source_inputs(files) or sha(ROOT / model['binary']) != model['binary_sha256']:
                model = sim.build('rv23_fp_branch_order', TOP, files)
                dump(model_path, model)
            trace = FOLDER / 'pipeline_commit.csv'
            run, log = sim.run([ROOT / model['binary'], f'+elf={(FOLDER / "test.elf").relative_to(ROOT).as_posix()}',
                f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+htif', '+quiet_commit',
                '+timeout_cycles=200000', '+expected_exit_code=0',
                *[f'+{name}={pc:x}' for name, pc in wrong_pcs().items()]], FOLDER / 'pipeline.log', 120)
        report.update(passed=True, pipeline_model=model, pipeline_run=run,
            pipeline=verify_pipeline(log), pipeline_trace_sha256=sha(trace))
        dump(FOLDER / 'report.json', report)
    print('PASS speculative FP recovery and slow owner kill', *check(), flush=True)


if __name__ == '__main__':
    main()

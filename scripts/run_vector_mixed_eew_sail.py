"""Compare the mixed-source EEW fixture on Sail and the native RV64 H/V SoC."""

import argparse
import json

from run_sail_event_comparison import compare, read_csv
from run_vector_overlap import ILLEGAL, SOURCE
from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/vector_mixed_eew_sail'


def compare_traces(sail_csv, rtl_csv):
    reference_rows, rtl_rows = read_csv(sail_csv), read_csv(rtl_csv)
    count, mismatch = compare(reference_rows, rtl_rows)
    assert mismatch is None, mismatch
    traps = [row for row in rtl_rows if row['trap'] == '1' and int(row['pc'], 16) >= 0x80000000]
    assert [int(row['cause']) for row in traps] == [2] * 7
    assert tuple(int(row['tval'], 16) for row in traps) == ILLEGAL[-7:]
    return count, traps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Audit the saved execution without rerunning it')
    args = parser.parse_args()
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    model_path = ROOT / 'out/rva23/hypervisor_integration/model.json'
    reference_path = ROOT / 'out/reference/sail-event-driver/report.json'
    model = json.loads(model_path.read_bytes())
    reference = json.loads(reference_path.read_bytes())
    assert reference['passed'] and {'-GXLEN=64', '-GHAS_V=1', '-GHAS_H=1'} <= set(model['params'])
    config = 'config/reference/sail-rv23.json'
    linker = 'scripts/reference/upstream_htif.ld'
    inputs = source_inputs([SOURCE, config, linker, 'scripts/run_vector_overlap.py',
                            'scripts/run_sail_event_comparison.py',
                            'tb/fixtures/bootrom/bootrom_host_jump64.hex'])
    inputs.update(model['inputs'])
    inputs.update(reference['inputs'])
    inputs.update({model['binary']: model['binary_sha256'],
                   reference['binary']: reference['binary_sha256']})
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path

    elf, sail_csv, rtl_csv = (folder / filename for filename in ('test.elf', 'sail.csv', 'commit.csv'))
    report_path = folder / 'report.json'
    if args.check:
        report = json.loads(report_path.read_bytes())
        assert report['passed'] and report['generator_sha256'] == sha(__file__)
        assert report['inputs'] == inputs and report['model'] == model
        assert report['reference_report_sha256'] == sha(reference_path)
        for path, key in ((elf, 'elf'), (sail_csv, 'sail_trace'), (rtl_csv, 'rtl_trace')):
            assert sha(path) == report[key + '_sha256'], path
        for phase in ('compile', 'sail', 'rtl'):
            run = report[phase]
            assert run['passed'] and run['exit_code'] == 0
            assert sha(ROOT / run['log']) == run['log_sha256']
        assert 'PASS Sail HTIF' in (ROOT / report['sail']['log']).read_text(encoding='utf-8')
        assert 'PASS rv32_program_tb' in (ROOT / report['rtl']['log']).read_text(encoding='utf-8')
        assert compare_traces(sail_csv, rtl_csv) == (report['events'], report['traps'])
        print('PASS current Sail/RTL mixed-EEW evidence', flush=True)
        return

    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-DMIXED_EEW_HTIF', '-nostdlib', '-nostartfiles', '-Wl,--no-relax',
            '-Wl,--build-id=none', '-T', linker, ROOT / SOURCE, '-o', elf], folder / 'compile.log', 60)
        elf_digest = sha(elf)
        original_path = sim.env['PATH']
        sim.env['PATH'] = 'C:/rv_toolchains/cygwin-rv23/bin;' + original_path
        sail, sail_log = sim.run([ROOT / reference['binary'], '--config', ROOT / config, '--commit-csv',
            sail_csv, '--inst-limit', '1000000', elf], folder / 'sail.log', 180)
        sim.env['PATH'] = original_path
        rtl, rtl_log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={rtl_csv.relative_to(ROOT).as_posix()}', '+quiet_commit', '+htif',
            '+timeout_cycles=100000', '+expected_exit_code=0'], folder / 'rtl.log', 120)

    assert 'PASS Sail HTIF' in sail_log and 'PASS rv32_program_tb' in rtl_log
    assert elf_digest == sha(elf)
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path
    count, traps = compare_traces(sail_csv, rtl_csv)
    dump(report_path, dict(passed=True, inputs=inputs, generator_sha256=sha(__file__),
        elf_sha256=elf_digest, sail_trace_sha256=sha(sail_csv), rtl_trace_sha256=sha(rtl_csv),
        model=model, reference_report_sha256=sha(reference_path), compile=compile_run,
        sail=sail, rtl=rtl, events=count, traps=traps))
    print(f'PASS exact Sail/RTL mixed-EEW comparison: {count} events, {len(traps)} precise traps', flush=True)


if __name__ == '__main__':
    main()

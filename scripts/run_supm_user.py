"""Exercise user-selected pointer masking through a native supervisor service."""
import csv
import json

from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/supm_user'
SOURCE = 'sw/tests/rv64_supm_user.S'
LINKER = 'scripts/reference/upstream_htif.ld'
BOOTROM = 'tb/fixtures/bootrom/bootrom_host_jump64.hex'
SAIL_CONFIG = 'config/reference/sail-rv23.json'
SAIL_REPORT = 'out/reference/sail-event-driver/report.json'
TAGGED_LOAD = 0x0004b303   # ld t1,0(s1)
TAGGED_STORE = 0x0054b023  # sd t0,0(s1)


def verify_trace(trace):
    observed = []
    expected_instruction = {5: TAGGED_LOAD, 7: TAGGED_STORE, 8: 0x73, 9: 0x73,
                            13: TAGGED_LOAD, 15: TAGGED_STORE}
    with trace.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if int(row['pc'], 16) < 0x40000000:
                continue
            word = int(row['instruction'], 16)
            if row['trap'] == '1':
                cause = int(row['cause'])
                assert word == expected_instruction[cause] and row['rd_write'] == '0', row
                observed.append(['trap', cause, int(row['tval'], 16)])
            elif row['csr_we'] == '1' and int(row['csr_addr'], 16) == 0x10a:
                observed.append(['senvcfg', int(row['csr_wdata'], 16)])
            elif word == TAGGED_LOAD:
                assert row['rd_write'] == '1' and int(row['rd']) == 6, row
                observed.append(['tagged_load', int(row['wdata'], 16)])
            elif word == TAGGED_STORE:
                observed.append(['tagged_store'])

    expected = []
    for load, store, address in [(5, 7, 0x80060000), (13, 15, 0x40060000)]:
        tagged = address | 0xfe00000000000000
        for pmm in [0, 0x200000000, 0]:
            expected += [['trap', 8, 0], ['senvcfg', pmm]]
            if pmm == 0:
                expected += [['trap', load, tagged], ['trap', store, tagged]]
            else:
                expected += [['tagged_load', 0x0123456789abcdef], ['tagged_store']]
        expected += [['trap', 8, 0], ['trap', 9, 0]]
    assert observed == expected, observed
    return observed


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_bytes())
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1', '-GHAS_MMU=1', '-GHAS_SSNPM=1'} <= set(model['params'])
    reference = json.loads((ROOT / SAIL_REPORT).read_bytes())
    assert reference['passed']
    runtime = {**reference['inputs'], reference['binary']: reference['binary_sha256'],
               **source_inputs([SOURCE, LINKER, BOOTROM, SAIL_CONFIG, SAIL_REPORT,
                                'scripts/run_sail_event_comparison.py'])}
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    source, elf, trace = ROOT / SOURCE, folder / 'test.elf', folder / 'commit.csv'
    sail_trace = folder / 'sail.csv'

    def fresh():
        for name, digest in inputs.items():
            assert sha(ROOT / name) == digest, name

    fresh()
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none', '-T', LINKER,
            source, '-o', elf], folder / 'compile.log', 60)
        elf_digest = sha(elf)
        original_path = sim.env['PATH']
        sim.env['PATH'] = 'C:/rv_toolchains/cygwin-rv23/bin;' + original_path
        sail, sail_log = sim.run([ROOT / reference['binary'], '--config', ROOT / SAIL_CONFIG,
            '--commit-csv', sail_trace, '--inst-limit', '100000', elf], folder / 'sail.log', 120)
        sim.env['PATH'] = original_path
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+htif', '+timeout_cycles=100000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    fresh()
    assert sha(elf) == elf_digest
    assert 'PASS Sail HTIF' in sail_log and '[host-finish code=0]' in log and 'PASS rv32_program_tb' in log
    matched_events, mismatch = compare(read_csv(sail_trace), read_csv(trace))
    assert mismatch is None, mismatch
    events = verify_trace(trace)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=elf_digest,
        trace_sha256=sha(trace), sail_trace_sha256=sha(sail_trace), compile=compile_run,
        run=run, sail=sail, matched_events=matched_events, events=events))
    print(f'PASS Supm user selection in Bare and Sv39: six selections, eight tagged faults, '
          f'{matched_events} matching Sail/RTL events', flush=True)


if __name__ == '__main__':
    main()

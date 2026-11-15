"""Check VS timer arithmetic, pending sources and delegated delivery."""
import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/guest_timer_wrap'
SOURCE = 'sw/tests/rv64_guest_timer_wrap.S'
MARKER = 'data=0x54494d57'


def verify_trace(trace):
    with trace.open(newline='') as stream:
        rows = [row for row in csv.DictReader(stream) if int(row['pc'], 16) >= 0x80000000]
    traps = [row for row in rows if row['trap'] == '1']
    assert [int(row['cause']) for row in traps] == [6, 10], traps
    assert [int(row['instruction'], 16) for row in traps] == [0, 0x73], traps
    pending = [int(row['wdata'], 16) & 0x40 for row in rows if row['instruction'] == '644027f3']
    assert pending == [0x40, 0, 0x40, 0, 0x40, 0x40, 0x40, 0, 0x40, 0], pending
    guest_time = [int(row['wdata'], 16) for row in rows if row['instruction'] == 'c0102573']
    assert len(guest_time) == 1 and 0x10000 <= guest_time[0] < 0x20000
    guest_cause = [int(row['wdata'], 16) for row in rows if row['instruction'] == '14202673']
    assert guest_cause == [0x8000000000000005]
    return dict(hip_pending=pending, guest_time=guest_time[0], guest_scause=guest_cause[0], traps=traps)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source, elf, trace = ROOT / SOURCE, folder / 'test.elf', folder / 'commit.csv'
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    runtime = source_inputs([SOURCE, 'tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    assert all(flag in model['params'] for flag in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'))
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh_sstc', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=100000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    assert MARKER in log and 'PASS rv32_program_tb' in log
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    outcomes = verify_trace(trace)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=sha(elf),
        trace_sha256=sha(trace), compile=compile_run, run=run, outcomes=outcomes))
    print('PASS RV64 guest timer wrap, independent VSTIP sources and delegated VS delivery')


if __name__ == '__main__':
    main()

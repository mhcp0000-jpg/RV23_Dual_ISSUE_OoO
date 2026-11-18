"""Exercise RVV overlap and restart rules through the RV64 H/V SoC."""
import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/vector_overlap'
SOURCE = 'sw/tests/rv64_vector_overlap.S'
MARKER = 'data=0x564f4c50'
SHARED_ILLEGAL = (
    0xd284a857, 0xb2848a57, 0x3a940a57, 0x5e842a57, 0xc2848a57, 0xd2849857, 0x26b58527,
    0x26b5d507, 0x2285d587, 0x4285d407, 0x1205d407, 0x00b58407, 0x2205df07,
)
ILLEGAL = (
    0xc2856457, 0xb280b4d7, 0x3a880457, 0x5e842457, 0x5e802657, 0x02822657, 0xc2856457,
) + SHARED_ILLEGAL
LEGAL = (0xc2956457, 0xb280b457, 0x6a854457, 0x02a50a57, 0x06a5d527)


def verify_trace(trace):
    with trace.open(newline='') as stream:
        rows = [row for row in csv.DictReader(stream) if int(row['pc'], 16) >= 0x80000000]
    traps = [row for row in rows if row['trap'] == '1']
    assert [int(row['cause']) for row in traps] == [2] * len(ILLEGAL), traps
    assert tuple(int(row['tval'], 16) for row in traps) == ILLEGAL, traps
    legal = [int(row['instruction'], 16) for row in rows if row['trap'] == '0'
             and int(row['instruction'], 16) in LEGAL]
    assert tuple(legal) == LEGAL, legal
    return dict(legal=legal, illegal=[int(row['tval'], 16) for row in traps])


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source, elf, trace = ROOT / SOURCE, folder / 'test.elf', folder / 'commit.csv'
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    runtime = source_inputs([SOURCE, 'tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    assert all(option in model['params'] for option in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'))
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh',
            '-mabi=lp64d', '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
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
    print(f'PASS RVV overlap and restart: {len(LEGAL)} legal operations and {len(ILLEGAL)} precise illegal traps')


if __name__ == '__main__':
    main()

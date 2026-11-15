"""Check committed Ssstateen permissions in HS and VS."""
import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/guest_stateen'
SOURCE = 'sw/tests/rv64_guest_stateen.S'
MARKER = 'data=0x53544154'
MASKS = (0, 1, 2, 4, 8, 16, 31)
CSRS = (0x10c, 0x10d, 0x10e, 0x10f, 0x10a, 0x60c)


def verify_trace(trace):
    csr_words = [csr << 20 | 0x02773 for csr in CSRS]
    expected = [(word, 0 if index < 5 and mask & (1 << index) else 22)
                for mask in MASKS for index, word in enumerate(csr_words)]
    observed = []
    ecalls = 0
    with trace.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if int(row['pc'], 16) < 0x80000000:
                continue
            word = int(row['instruction'], 16)
            if row['trap'] == '1':
                cause = int(row['cause'])
                if cause == 10 and word == 0x73:
                    ecalls += 1
                    continue
                assert cause == 22 and int(row['tval'], 16) == word
                observed.append((word, cause))
            elif word in csr_words:
                assert int(row['wdata'], 16) == int(word >> 20 == 0x10a)
                observed.append((word, 0))
    assert observed == expected and ecalls == len(MASKS), observed
    return dict(cases=len(expected), virtual_instruction_traps=sum(cause == 22 for _, cause in observed),
                guest_ecalls=ecalls)


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
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh_smstateen',
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
    print('PASS native Ssstateen', outcomes)


if __name__ == '__main__':
    main()

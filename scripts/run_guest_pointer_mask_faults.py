"""Check transformed guest trap addresses through vector, AMO and CBO paths."""

import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/guest_pointer_mask_faults'
BASE = 'sw/tests/rv64_hypervisor_vector_faults.S'
MARKER = 'data=0x504d4737'


def fixture():
    assembly = (ROOT / BASE).read_text(encoding='utf-8')
    replacements = [
        ('  li t0,0xc0000000000000f0\n  csrw henvcfg,t0',
         '  li t0,(0xc0000000000000f0 | (MASK_PMM << 32))\n  csrw henvcfg,t0\n'
         '  csrr t1,henvcfg\n  bne t1,t0,fail'),
        ('guest_entry:\n  li s0,0x400a3ff0\n  li s1,0x400a4000',
         'guest_entry:\n  li s0,0xfe000000400a3ff0\n  li s1,0xfe000000400a4000'),
        ('  li t1,0x48595035', '  li t1,0x504d4737'),
    ]
    for original, replacement in replacements:
        assert assembly.count(original) == 1, original
        assembly = assembly.replace(original, replacement)
    return assembly


def traps(path):
    with path.open(newline='') as stream:
        return [row for row in csv.DictReader(stream)
                if row['trap'] == '1' and int(row['pc'], 16) >= 0x40000000]


def verify_trace(path):
    records = traps(path)
    assert [int(row['cause']) for row in records] == [23, 10, 21, 10, 23, 23, 10]
    assert [int(row['tval'], 16) for row in records if int(row['cause']) != 10] == [0x400a4000] * 4
    return records


def verify_control(path):
    records = traps(path)
    assert len(records) == 1 and int(records[0]['cause']) == 15, records
    assert int(records[0]['tval'], 16) == 0xfe000000400a3ff0, records
    return records


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'test.S'
    source.write_text(fixture(), encoding='utf-8')
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']
    runtime = source_inputs([BASE, 'tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])

    def fresh():
        assert source_inputs(files) == model['inputs']
        assert sha(ROOT / model['binary']) == model['binary_sha256']
        for path, digest in runtime.items():
            assert sha(ROOT / path) == digest, path

    assert all(p in model['params'] for p in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1', '-GHAS_SSNPM=1'))
    fresh()
    results = {}
    with Simulator() as sim:
        for pmm, name in ((2, 'test'), (0, 'disabled')):
            elf = folder / f'{name}.elf'
            trace = folder / ('commit.csv' if pmm else 'disabled.csv')
            compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh_zicboz', '-mabi=lp64d',
                '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none', f'-DMASK_PMM={pmm}',
                '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / f'{name}.compile.log', 60)
            run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
                f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
                '+timeout_cycles=300000', f'+expected_exit_code={0 if pmm else 1}'],
                folder / f'{name}.simulation.log', 120)
            assert 'PASS rv32_program_tb' in log
            assert (MARKER in log) if pmm else ('[host-finish code=1]' in log)
            results[name] = dict(compile=compile_run, run=run, elf_sha256=sha(elf), trace_sha256=sha(trace),
                                 traps=verify_trace(trace) if pmm else verify_control(trace))
    fresh()
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(__file__), source_sha256=sha(source),
        disabled=results['disabled'], **results['test']))
    print('PASS guest pointer masking: 4 transformed G-stage traps; masking-disabled control observed VS fault',
          flush=True)


if __name__ == '__main__':
    main()


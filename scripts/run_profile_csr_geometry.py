"""Check trap-vector bases, supported translation modes and UXL on full H/V RTL.

This M-mode CSR roundtrip test complements actual S/VS translation/trap ELFs;
it does not itself perform page walks or execute at every vector address.
"""
import csv
import json

from sim_runner import ROOT, Simulator, GCC, dump, sha, source_inputs


def main():
    folder = ROOT / 'out/rva23/profile_csr_geometry'
    folder.mkdir(parents=True, exist_ok=True)
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    assert all(p in model['params'] for p in ['-GHAS_H=1', '-GHAS_V=1', '-GXLEN=64'])
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']
    runtime = {p: sha(ROOT / p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex',
                                         'sw/benchmarks/coremark/rv32_tim.ld']}

    def fresh():
        assert source_inputs(files) == model['inputs']
        assert sha(ROOT / model['binary']) == model['binary_sha256']
        for p, digest in runtime.items():
            assert sha(ROOT / p) == digest

    fresh()
    cases = []
    lines = ['.section .text.init,"ax"', '.option norvc', '.option norelax',
             '.globl _start', '_start:', 'la t0,fail', 'csrw mtvec,t0', 'csrw mie,zero']

    def check(csr, value, expected, mask=(1 << 64) - 1, contract=''):
        cases.append(dict(id=len(cases) + 1, csr=csr, value=value,
                          expected=expected, mask=mask, contract=contract))
        lines.extend([f'li s0,{len(cases)}', f'li t0,0x{value:016x}', f'csrw {csr},t0',
                      f'csrr t1,{csr}', f'li t2,0x{mask:016x}', 'and t1,t1,t2',
                      f'li t2,0x{expected:016x}', 'bne t1,t2,fail'])

    # Canonical Sv39 low and high virtual ranges, walking all address bits.
    bases = {0, 0x80000000, 0x800ffffc, 0xffffffc000000000, 0xfffffffffffffffc}
    for bit in range(2, 38):
        bases.add(1 << bit)
        bases.add(0xffffffc000000000 | (1 << bit))
    for csr, contract in [('stvec', 'Sstvecd'), ('vstvec', 'Shvstvecd')]:
        for base in sorted(bases):
            check(csr, base, base, contract=contract)
        check(csr, 0, 0, contract=contract)

    # M-mode fetches bypass S/VS/G translation while testing CSR capabilities.
    # Unsupported modes must ignore the entire write, preserving the old root.
    root = 0x8000000000080030
    for csr in ['satp', 'vsatp', 'hgatp']:
        for previous in [0, root]:
            check(csr, previous, previous, contract='Svbare/Sv39/Shvsatpa/Shgatpa')
            for unsupported in [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15]:
                check(csr, (unsupported << 60) | 0x80040, previous,
                      contract='Unsupported MODE write preserves complete CSR')
        check(csr, 0, 0, contract='Svbare')
    # UXL=64 must remain available in both physical and virtual S views.
    for csr in ['sstatus', 'vsstatus']:
        for requested in range(4):
            check(csr, requested << 32, 2 << 32, 3 << 32, contract='Ssu64xl')
    # Ssstateen requires all four S and H views. This core has no optional
    # sstateen-controlled state; H implements SE and index-0 ENVCFG.
    for index in range(4):
        implemented = (1 << 63) | ((1 << 62) if index == 0 else 0)
        for value in [0, (1 << 64) - 1, 1 << 63, 1 << 62]:
            check(f'hstateen{index}', value, value & implemented, contract='Ssstateen H view')
        for value in [0, (1 << 64) - 1]:
            check(f'sstateen{index}', value, 0, contract='Ssstateen S view, no optional state')
    lines += ['lui t0,0x10000', 'li t1,0x43535247', 'sw t1,0xc(t0)',
              'sw zero,0x14(t0)', 'halt:j halt', 'fail:', 'lui t0,0x10000',
              'sw s0,0xc(t0)', 'li t1,1', 'sw t1,0x14(t0)', 'j halt']
    source, elf, trace = folder / 'test.S', folder / 'test.elf', folder / 'commit.csv'
    source.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    dump(folder / 'cases.json', cases)
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, text = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=1000000', '+expected_exit_code=0'], folder / 'simulation.log', 180)
    fresh()
    assert 'PASS rv32_program_tb' in text and 'data=0x43535247' in text
    with trace.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert not [r for r in rows if r['trap'] == '1' and int(r['pc'], 16) >= 0x80000000]
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        scope='M-mode CSR roundtrips for S/VS vector bases, Bare/Sv39/Sv39x4 MODE, RV64 UXL and eight state-enable views; finite coverage',
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=sha(elf),
        trace_sha256=sha(trace), cases_sha256=sha(folder / 'cases.json'),
        compile=compile_run, run=run, case_count=len(cases), vector_bases=len(bases)))
    print('PASS profile CSR geometry:', len(cases), 'cases,', len(bases), 'bases per S/VS vector', flush=True)


if __name__ == '__main__':
    main()

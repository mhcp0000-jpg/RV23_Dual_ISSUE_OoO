"""Check CSR geometry and native Sv39 direct trap entry on full H/V RTL."""
import argparse
import csv
import json

from sim_runner import ROOT, Simulator, GCC, dump, sha, source_inputs

DIRECT_VECTORS = [(guest, alias, offset) for guest in (False, True)
                  for alias in (0x40000000, 0xffffffc000000000, 0xffffffffc0000000)
                  for offset in (4, 0xffc)]


def direct_vector_trace(rows):
    traps = [(index, row) for index, row in enumerate(rows)
             if row['trap'] == '1' and int(row['pc'], 16) >= 0x80000000]
    expected_causes = [cause for guest, _, _ in DIRECT_VECTORS for cause in (3, 10 if guest else 9)]
    assert [int(row['cause']) for _, row in traps] == expected_causes
    entries = [int(rows[index + 1]['pc'], 16) for index, _ in traps[::2]]
    for entry, (_, alias, offset) in zip(entries, DIRECT_VECTORS, strict=True):
        assert entry & ~0x3fffffff == alias and entry & 0xfff == offset
    return entries


def fixture():
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
    # SATP/VSATP ignore unsupported MODE writes. HGATP preserves only MODE
    # while the other WARL fields are updated.
    root = 0x8000000000080030
    for csr in ['satp', 'vsatp', 'hgatp']:
        for previous in [0, root]:
            check(csr, previous, previous, contract='Svbare/Sv39/Shvsatpa/Shgatpa')
            for index, unsupported in enumerate([1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15]):
                if csr == 'hgatp':
                    requested_ppn = 0x80043 + 4 * index
                    value = (unsupported << 60) | (0x155 << 44) | requested_ppn
                    expected = ((previous >> 60) << 60) | (requested_ppn & ~3)
                    check(csr, value, expected, contract='HGATP unsupported MODE preserves MODE and updates PPN')
                else:
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
    # One Sv39 root maps the same executable SRAM into identity, low and
    # two high virtual ranges. The last handler starts at a page's final word.
    lines += ['li t0,-1', 'csrw pmpaddr0,t0', 'li t0,31', 'csrw pmpcfg0,t0',
              'la t0,root', 'li t1,0x200000cb', 'sd t1,8(t0)', 'sd t1,16(t0)',
              'li t2,2048', 'add t2,t2,t0', 'sd t1,0(t2)', 'sd t1,2040(t2)',
              'srli s1,t0,12', 'li t1,0x8000000000000000', 'or s1,s1,t1',
              'la t0,return_to_m', 'csrw mtvec,t0', 'li t0,8', 'csrw medeleg,t0',
              'j vector_setup_0']
    for index, (guest, alias, offset) in enumerate(DIRECT_VECTORS):
        lines += [f'vector_setup_{index}:', f'li s0,{len(cases) + index + 1}',
                  f'la s2,vector_{offset}', 'slli s2,s2,34', 'srli s2,s2,34',
                  f'li t0,{alias:#x}', 'or s2,s2,t0',
                  f'csrw {"vstvec" if guest else "stvec"},s2',
                  f'csrr t0,{"vstvec" if guest else "stvec"}', 'bne t0,s2,fail',
                  f'li t0,{8 if guest else 0}', 'csrw hedeleg,t0',
                  'csrw satp,s1', 'csrw vsatp,s1', 'sfence.vma', 'hfence.vvma',
                  f'li t0,{0x800 | (int(guest) << 39):#x}', 'csrw mstatus,t0',
                  f'li s3,{10 if guest else 9}', 'la s4,vector_probe',
                  f'la s5,{"finish" if index + 1 == len(DIRECT_VECTORS) else f"vector_setup_{index + 1}"}',
                  'li a1,0', 'csrw mepc,s4', 'mret']
    lines += ['vector_probe:', 'ebreak', 'ecall', 'j fail',
              'return_to_m:', 'csrr t0,mcause', 'bne t0,s3,fail', 'li t0,1',
              'bne a1,t0,fail', 'csrr t0,mepc', 'addi t1,s4,4', 'bne t0,t1,fail', 'jr s5',
              'finish:', 'lui t0,0x10000', 'li t1,0x43535247', 'sw t1,0xc(t0)',
              'sw zero,0x14(t0)', 'halt:j halt', 'fail:', 'lui t0,0x10000',
              'sw s0,0xc(t0)', 'li t1,1', 'sw t1,0x14(t0)', 'j halt',
              '.balign 4096', '.space 4', 'vector_4:', 'auipc t0,0', 'j check_vector_pc',
              '.balign 4096', '.space 4092', 'vector_4092:', 'auipc t0,0', 'j check_vector_pc',
              'check_vector_pc:', 'bne t0,s2,vector_fail', 'csrr t0,scause', 'li t1,3',
              'bne t0,t1,vector_fail', 'csrr t0,sepc', 'bne t0,s4,vector_fail',
              'addi t0,t0,4', 'csrw sepc,t0', 'addi a1,a1,1', 'sret',
              'vector_fail:', 'li a1,-1', 'ecall', 'j vector_fail',
              '.section .bss,"aw",@nobits', '.balign 4096', 'root:.space 4096']
    return '\n'.join(lines) + '\n', cases, len(bases)


def execute(sim, binary, elf, folder, *, before=False):
    trace = folder / ('replay-before.csv' if before else 'commit.csv')
    log = folder / ('replay-before.log' if before else 'simulation.log')
    run, text = sim.run([binary, f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
        '+timeout_cycles=1000000', '+expected_exit_code=0'], log, 180,
        expected_failure='ELF reported failure exit code 1' if before else None)
    return run, text, trace


def compare_before(archive, current, cases, code, runtime):
    before = json.loads((archive / 'model.json').read_bytes())
    old_binary, old_csr, elf = (archive / name for name in ('before.exe', 'before.sv', 'test.elf'))
    csr = 'rtl/backend/rv_hypervisor_csrs.sv'
    assert current['params'] == before['params'] and current['inputs'].keys() == before['inputs'].keys()
    assert {name for name, digest in current['inputs'].items() if digest != before['inputs'][name]} == {csr}
    assert sha(old_csr) == before['inputs'][csr] and sha(old_binary) == before['binary_sha256']
    assert (archive / 'test.S').read_text(encoding='utf-8') == code
    assert json.loads((archive / 'cases.json').read_bytes()) == cases
    expected = next(case['id'] for case in cases if case['csr'] == 'hgatp' and case['value'] >> 60 not in (0, 8))
    digest = sha(elf)
    folder = ROOT / 'out/rva23/hgatp_warl_comparison'
    folder.mkdir(parents=True, exist_ok=True)
    with Simulator() as sim:
        rejected, negative, negative_trace = execute(sim, old_binary, elf, folder, before=True)
        assert f'data=0x{expected:08x}' in negative
        assert sha(elf) == digest
        run, text, trace = execute(sim, ROOT / current['binary'], elf, folder)
    assert sha(elf) == digest
    assert 'data=0x43535247' in text and 'PASS rv32_program_tb' in text
    with trace.open(newline='') as stream:
        entries = direct_vector_trace(list(csv.DictReader(stream)))
    artifacts = (elf, old_binary, old_csr, archive / 'model.json', archive / 'test.S',
                 archive / 'cases.json', negative_trace, trace)
    dump(folder / 'report.json', dict(passed=True, rejected_before_case=expected, elf_sha256=digest,
        driver_sha256=sha(__file__), model=current, runtime_inputs=runtime, before=rejected, after=run,
        artifacts={path.relative_to(ROOT).as_posix(): sha(path) for path in artifacts}, direct_entries=entries))
    print(f'PASS exact-ELF HGATP comparison: old model rejected case {expected}, corrected SoC passed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare-before', help='Directory containing the saved pre-fix model and test ELF')
    args = parser.parse_args()
    folder = ROOT / 'out/rva23/profile_csr_geometry'
    folder.mkdir(parents=True, exist_ok=True)
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_bytes())
    assert all(p in model['params'] for p in ['-GHAS_H=1', '-GHAS_V=1', '-GXLEN=64'])
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']
    runtime = source_inputs(['tb/fixtures/bootrom/bootrom_host_jump64.hex', 'sw/benchmarks/coremark/rv32_tim.ld'])

    def fresh():
        assert source_inputs(files) == model['inputs']
        assert sha(ROOT / model['binary']) == model['binary_sha256']
        assert runtime == source_inputs(runtime)

    fresh()
    code, cases, bases = fixture()
    if args.compare_before:
        compare_before((ROOT / args.compare_before).resolve(strict=True), model, cases, code, runtime)
        fresh()
        return
    source, elf, trace = folder / 'test.S', folder / 'test.elf', folder / 'commit.csv'
    source.write_text(code, encoding='utf-8')
    dump(folder / 'cases.json', cases)
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, text, trace = execute(sim, ROOT / model['binary'], elf, folder)
    fresh()
    assert 'PASS rv32_program_tb' in text and 'data=0x43535247' in text
    with trace.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    vector_entries = direct_vector_trace(rows)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        scope='M-mode CSR roundtrips for S/VS vector bases, Bare/Sv39/Sv39x4 MODE, RV64 UXL and eight state-enable views; native S/VS Sv39 direct trap entry',
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=sha(elf),
        trace_sha256=sha(trace), cases_sha256=sha(folder / 'cases.json'),
        compile=compile_run, run=run, case_count=len(cases), vector_bases=bases,
        direct_vector_entries=vector_entries))
    print('PASS profile CSR geometry:', len(cases), 'cases,', bases, 'bases per S/VS vector,',
          len(vector_entries), 'native direct entries', flush=True)


if __name__ == '__main__':
    main()

"""Execute counter gates and RV64 CSR forms in M/HS/VS/U/VU on one H/V SoC.

Expected traps follow Privileged ISA 1.13: machine denial has cause 2,
guest H/S denial has cause 22, and RV64 high halves/read-only writes have
cause 2 even when the corresponding low-half read is guest-intercepted.
"""
import argparse
import csv
import itertools
import json

from sim_runner import ROOT, Simulator, GCC, dump, sha, source_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--form', choices=['read', 'high', 'write_zero'], required=True)
    args = parser.parse_args()
    folder = ROOT / 'out/rva23/counter_permission_matrix' / args.form
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
        for p, digest in runtime.items():
            assert sha(ROOT / p) == digest
        assert sha(ROOT / model['binary']) == model['binary_sha256']

    fresh()
    cases = []
    for mode, index, (mg, hg, sg), form in itertools.product(
            ['M', 'HS', 'VS', 'U', 'VU'], [0, 1, 2, 3, 4, 5, 6, 31],
            itertools.product(range(2), repeat=3), [args.form]):
        effective_m = mg if index < 7 else 0
        effective_h = hg if index < 7 else 0
        effective_s = sg if index < 7 else 0
        cause = 0
        if form != 'read':
            cause = 2
        elif mode != 'M':
            if not effective_m:
                cause = 2
            elif mode in ['VS', 'VU'] and (not effective_h or mode == 'VU' and not effective_s):
                cause = 22
            elif mode == 'U' and not effective_s:
                cause = 2
        address = 0xc00 + index + (0x80 if form == 'high' else 0)
        opcode = (address << 20) | (0x1073 if form == 'write_zero' else 0x22f3)
        cases.append(dict(id=len(cases) + 1, mode=mode, index=index, form=form,
                          mg=mg, hg=hg, sg=sg, cause=cause, opcode=opcode))

    lines = ['.section .text.init,"ax"', '.option norvc', '.option norelax',
             '.globl _start', '_start:', 'la t0,m_trap', 'csrw mtvec,t0',
             'li t0,-1', 'csrw pmpaddr0,t0', 'li t0,31', 'csrw pmpcfg0,t0',
             'csrw medeleg,zero', 'csrw mie,zero', 'li s10,0']
    # Check all supported enable bits independently of individual counter reads.
    for csr in ['mcounteren', 'hcounteren', 'scounteren']:
        lines += ['li t0,-1', f'csrw {csr},t0', f'csrr t1,{csr}',
                  'li t2,127', 'bne t1,t2,fail']
    lines += ['j setup_1']
    for c in cases:
        n, mode = c['id'], c['mode']
        privilege = 3 if mode == 'M' else 1 if mode in ['HS', 'VS'] else 0
        status = (privilege << 11) | (int(mode in ['VS', 'VU']) << 39)
        ecall = {'M': 11, 'HS': 9, 'VS': 10, 'U': 8, 'VU': 8}[mode]
        c['ecall_cause'] = ecall
        lines += [f'setup_{n}:', f'li s0,{n}', f'li s1,{c["cause"]}', f'li s2,{c["opcode"]}',
                  f'la s3,probe_{n}', f'la s4,after_{n}', f'la s11,ecall_{n}',
                  f'la s5,{"finish" if n == len(cases) else "setup_" + str(n + 1)}',
                  'li s6,0', f'li s8,{ecall}', f'li s9,{status}']
        for csr, gate in [('mcounteren', 'mg'), ('hcounteren', 'hg'), ('scounteren', 'sg')]:
            value = c[gate] << c['index']
            expected = value if c['index'] < 7 else 0
            lines += [f'li t0,{value}', f'csrw {csr},t0', f'csrr t1,{csr}',
                      f'li t2,{expected}', 'bne t1,t2,fail']
        lines += [f'li t0,{status}', 'csrw mstatus,t0']
        lines += [f'j probe_{n}'] if mode == 'M' else [f'la t0,probe_{n}', 'csrw mepc,t0', 'mret']
        lines += [f'probe_{n}:', f'.word {c["opcode"]}', f'after_{n}:']
        if not c['cause'] and c['index'] == 31:
            lines += ['bnez t0,fail']
        lines += [f'ecall_{n}:', 'ecall', 'j fail']
    lines += ['m_trap:', 'csrr t0,mcause', 'beq t0,s8,case_done',
              'beqz s1,fail', 'bne t0,s1,fail', 'bnez s6,fail',
              'csrr t0,mtval', 'bne t0,s2,fail', 'csrr t0,mepc', 'bne t0,s3,fail',
              'csrr t0,mstatus', 'li t1,0x8000001800', 'and t0,t0,t1', 'bne t0,s9,fail',
              'li s6,1', 'csrw mepc,s4', 'mret', 'case_done:',
              'csrr t0,mepc', 'bne t0,s11,fail', 'snez t0,s1', 'bne t0,s6,fail',
              'addi s10,s10,1', 'csrw mstatus,zero', 'jr s5', 'finish:',
              f'li t0,{len(cases)}', 'bne s10,t0,fail', 'lui t0,0x10000',
              'li t1,0x43545250', 'sw t1,0xc(t0)', 'sw zero,0x14(t0)', 'halt:j halt',
              'fail:', 'lui t0,0x10000', 'sw s0,0xc(t0)', 'li t1,1', 'sw t1,0x14(t0)', 'j halt']
    source, elf, trace = folder / 'test.S', folder / 'test.elf', folder / 'commit.csv'
    source.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    dump(folder / 'cases.json', cases)
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, text = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=2000000', '+expected_exit_code=0'], folder / 'simulation.log', 360)
    fresh()
    assert 'PASS rv32_program_tb' in text and 'data=0x43545250' in text
    with trace.open(newline='') as stream:
        traps = [r for r in csv.DictReader(stream) if r['trap'] == '1' and int(r['pc'], 16) >= 0x80000000]
    expected = []
    for c in cases:
        if c['cause']:
            expected.append(c['cause'])
        expected.append(c['ecall_cause'])
    assert [int(r['cause']) for r in traps] == expected
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        scope='Counter gate priority and read-only/high-half CSR traps; M/HS/VS/U/VU; finite coverage',
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=sha(elf),
        cases_sha256=sha(folder / 'cases.json'), trace_sha256=sha(trace),
        compile=compile_run, run=run, case_count=len(cases), trap_count=len(traps)))
    print('PASS counter permission matrix:', len(cases), 'cases,', len(traps), 'precise traps', flush=True)


if __name__ == '__main__':
    main()

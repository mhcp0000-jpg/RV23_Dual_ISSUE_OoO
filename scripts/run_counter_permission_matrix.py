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


MODES = ('M', 'HS', 'VS', 'U', 'VU')


def counter_cases(form):
    for mode, index, (mg, hg, sg) in itertools.product(
            MODES, [0, 1, 2, 3, 4, 5, 6, 31], itertools.product(range(2), repeat=3)):
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
        yield dict(mode=mode, index=index, form=form, mg=mg, hg=hg, sg=sg, cause=cause, opcode=opcode)


def timer_cases(form):
    opcode_base = 0x22f3 if form == 'timer_read' else 0x712f3  # t0 <- CSR; write operand is a4
    for mode, address, (m_enable, h_enable, m_stce, h_stce) in itertools.product(
            MODES, (0x14d, 0x24d), itertools.product(range(2), repeat=4)):
        cause = 0
        if mode != 'M':
            if not (m_enable and m_stce) or mode == 'U':
                cause = 2
            elif mode == 'VU' or (mode == 'VS' and (address == 0x24d or not (h_enable and h_stce))):
                cause = 22
        yield dict(mode=mode, form=form, cause=cause, opcode=address << 20 | opcode_base,
                   mg=m_enable, hg=h_enable, m_stce=m_stce, h_stce=h_stce,
                   value=0x5678 if mode == 'VS' or address == 0x24d else 0x1234)


def timer_setup(case):
    return [
        'li t0,0x1234', 'csrw 0x14d,t0', 'li t0,0x5678', 'csrw 0x24d,t0',
        'li a4,0x9abc', f'li t0,{case["mg"] << 1}', 'csrw mcounteren,t0',
        f'li t0,{case["hg"] << 1}', 'csrw hcounteren,t0',
        f'li t0,{case["m_stce"] << 63}', 'csrw menvcfg,t0',
        f'li t0,{case["h_stce"] << 63}', 'csrw henvcfg,t0',
        'csrr t1,henvcfg', 'srli t1,t1,63',
        f'li t2,{case["m_stce"] & case["h_stce"]}', 'bne t1,t2,fail',
    ]


def verify_timer_trace(trace, cases):
    def probe(row):
        opcode = int(row['instruction'], 16)
        if row['trap'] == '1':
            assert int(row['tval'], 16) == opcode
            return opcode, int(row['cause']), None
        assert row['gpr_we'] == '1' and int(row['rd']) == 5
        return opcode, 0, int(row['wdata'], 16)

    probes = {case['opcode'] for case in cases}
    with trace.open(newline='') as stream:
        rows = csv.DictReader(stream)
        observed = [probe(row) for row in rows if int(row['pc'], 16) >= 0x80000000
                    and int(row['instruction'], 16) in probes]
    assert observed == [(case['opcode'], case['cause'], None if case['cause'] else case['value'])
                        for case in cases]
    return dict(accesses=len(observed), legal=sum(cause == 0 for _, cause, _ in observed),
                illegal=sum(cause == 2 for _, cause, _ in observed),
                virtual=sum(cause == 22 for _, cause, _ in observed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--form', choices=['read', 'high', 'write_zero', 'timer_read', 'timer_write'], required=True)
    args = parser.parse_args()
    timer = args.form.startswith('timer_')
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
    generate_cases = timer_cases if timer else counter_cases
    cases = [dict(case, id=index) for index, case in enumerate(generate_cases(args.form), 1)]

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
        if timer:
            lines += timer_setup(c)
        else:
            for csr, gate in [('mcounteren', 'mg'), ('hcounteren', 'hg'), ('scounteren', 'sg')]:
                value = c[gate] << c['index']
                expected = value if c['index'] < 7 else 0
                lines += [f'li t0,{value}', f'csrw {csr},t0', f'csrr t1,{csr}',
                          f'li t2,{expected}', 'bne t1,t2,fail']
        lines += [f'li t0,{status}', 'csrw mstatus,t0']
        lines += [f'j probe_{n}'] if mode == 'M' else [f'la t0,probe_{n}', 'csrw mepc,t0', 'mret']
        lines += [f'probe_{n}:', f'.word {c["opcode"]}', f'after_{n}:']
        if timer and not c['cause']:
            lines += [f'li t1,{c["value"]}', 'bne t0,t1,fail']
            if args.form == 'timer_write':
                lines += [f'csrr t0,{c["opcode"] >> 20}', 'bne t0,a4,fail']
        elif not timer and not c['cause'] and c['index'] == 31:
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
    timer_evidence = {'timer_accesses': verify_timer_trace(trace, cases)} if timer else {}
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        scope=('Sstc CSR permission, alias, read and write in M/HS/VS/U/VU' if timer else
               'Counter gate priority and read-only/high-half CSR traps; M/HS/VS/U/VU; finite coverage'),
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=sha(elf),
        cases_sha256=sha(folder / 'cases.json'), trace_sha256=sha(trace),
        compile=compile_run, run=run, case_count=len(cases), trap_count=len(traps), **timer_evidence))
    print('PASS counter permission matrix:', len(cases), 'cases,', len(traps), 'precise traps', flush=True)


if __name__ == '__main__':
    main()

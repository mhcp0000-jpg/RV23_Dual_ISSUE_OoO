"""Check Zawrs STO and guest NTO timeout priority on the production H/V SoC."""

import csv
import itertools
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


CASES = [(mode, tw, vtw) for mode, (tw, vtw) in
         itertools.product(('VS', 'VU'), ((0, 1), (1, 0), (1, 1)))]
MARKER = '0x57525348'


def fixture():
    lines = [
        '.section .text.init,"ax"', '.option norvc', '.option norelax', '.globl _start',
        '_start:', 'la t0,trap', 'csrw mtvec,t0', 'csrw medeleg,zero', 'csrw mie,zero',
        'li t0,-1', 'csrw pmpaddr0,t0', 'li t0,31', 'csrw pmpcfg0,t0',
        'li s8,0x80070000', 'sd zero,0(s8)',
    ]
    for index, (mode, tw, vtw) in enumerate(CASES):
        status = (1 << 39) | ((mode == 'VS') << 11) | (tw << 21)
        next_case = f'setup_{index + 1}' if index + 1 < len(CASES) else 'finish'
        lines += [
            f'setup_{index}:', f'li s0,{index + 1}', f'li s1,{2 if tw else 22}',
            f'li s2,{10 if mode == "VS" else 8}', f'li s3,{status}',
            f'la s4,timeout_{index}', f'la s5,ecall_{index}', f'la s6,{next_case}',
            'li s7,0', f'li t0,{vtw << 21}', 'csrw hstatus,t0',
            'csrr t1,hstatus', 'li t2,0x200000', 'and t1,t1,t2', 'bne t1,t0,fail',
            'csrw mstatus,s3', f'la t0,entry_{index}', 'csrw mepc,t0', 'mret',
            f'entry_{index}:', 'wrs.nto',
            'lr.d t0,(s8)', 'wrs.sto', 'sc.d t0,zero,(s8)', 'bnez t0,fail',
            'lr.d t0,(s8)', f'timeout_{index}:', 'wrs.nto',
            'beqz s7,fail', 'wrs.nto',
            f'ecall_{index}:', 'ecall', 'j fail',
        ]
    lines += [
        'trap:', 'csrr t0,mstatus', 'li t1,0x8000201800', 'and t0,t0,t1',
        'bne t0,s3,fail', 'csrr t0,mcause', 'beq t0,s2,done',
        'bne t0,s1,fail', 'bnez s7,fail', 'csrr t0,mepc', 'bne t0,s4,fail',
        'csrr t0,mtval', 'li t1,0x00d00073', 'bne t0,t1,fail', 'li s7,1',
        'addi t0,s4,4', 'csrw mepc,t0', 'mret',
        'done:', 'csrr t0,mepc', 'bne t0,s5,fail', 'beqz s7,fail', 'jr s6',
        'finish:', 'lui t0,0x10000', f'li t1,{MARKER}', 'sw t1,0xc(t0)',
        'sw zero,0x14(t0)', 'halt: j halt',
        'fail:', 'lui t0,0x10000', 'sw s0,0xc(t0)', 'li t1,1', 'sw t1,0x14(t0)', 'j halt',
    ]
    return '\n'.join(lines) + '\n'


def verify_trace(path):
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    rows = [row for row in rows if int(row['pc'], 16) >= 0x80000000]
    traps = [row for row in rows if row['trap'] == '1']
    expected = [cause for mode, tw, _ in CASES for cause in (2 if tw else 22, 10 if mode == 'VS' else 8)]
    assert [int(row['cause']) for row in traps] == expected, traps
    for row in traps[::2]:
        assert int(row['instruction'], 16) == int(row['tval'], 16) == 0x00d00073, row
    waits = [row for row in rows if int(row['instruction'], 16) in (0x00d00073, 0x01d00073)]
    sequence = [(0x00d00073, '0'), (0x01d00073, '0'), (0x00d00073, '1'), (0x00d00073, '0')]
    assert [(int(row['instruction'], 16), row['trap']) for row in waits] == sequence * len(CASES)
    sc = [row for row in rows if (int(row['instruction'], 16) & 0xf800707f) == 0x1800302f]
    assert len(sc) == len(CASES) and all(row['gpr_we'] == '1' and int(row['wdata'], 16) == 0 for row in sc), sc
    latencies = []
    for previous, row in zip(rows, rows[1:]):
        opcode = int(row['instruction'], 16)
        if opcode == 0x01d00073 or (opcode == 0x00d00073 and row['trap'] == '1'):
            assert (int(previous['instruction'], 16) & 0xf800707f) == 0x1000302f, previous
            elapsed = int(row['cycle']) - int(previous['cycle'])
            minimum = 2048 if row['trap'] == '1' else 1024
            assert minimum <= elapsed <= minimum + 100, (row, elapsed)
            latencies.append(elapsed)
    assert len(latencies) == 2 * len(CASES)
    return dict(traps=traps, sto_sc_pairs=len(sc), lr_to_sto_cycles=latencies[::2],
                lr_to_nto_trap_cycles=latencies[1::2])


def main():
    folder = ROOT / 'out/rva23/guest_wrs_timeout'
    folder.mkdir(parents=True, exist_ok=True)
    source, elf, trace = (folder / name for name in ('test.S', 'test.elf', 'commit.csv'))
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']
    runtime = source_inputs(['tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])

    def fresh():
        assert source_inputs(files) == model['inputs']
        assert sha(ROOT / model['binary']) == model['binary_sha256']
        for path, digest in runtime.items():
            assert sha(ROOT / path) == digest, path

    assert all(p in model['params'] for p in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1', '-GHAS_ZAWRS=1'))
    fresh()
    source.write_text(fixture(), encoding='utf-8')
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh_zawrs', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=1000000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    fresh()
    assert 'PASS rv32_program_tb' in log and f'data={MARKER}' in log, log[-3000:]
    evidence = verify_trace(trace)
    dump(folder / 'report.json', dict(
        passed=True, model=model, runtime_inputs=runtime, generator_sha256=sha(__file__),
        source_sha256=sha(source), elf_sha256=sha(elf), trace_sha256=sha(trace),
        compile=compile_run, run=run, cases=CASES, **evidence))
    print('PASS native guest WRS: 6 TW/VTW contexts, 6 STO/SC pairs, 12 exact traps', flush=True)


if __name__ == '__main__':
    main()


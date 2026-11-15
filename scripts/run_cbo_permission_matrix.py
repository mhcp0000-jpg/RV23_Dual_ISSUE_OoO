"""Exercise CBO privilege gates, precise traps and 64-byte zeroing on the H/V SoC."""

import csv
import itertools
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/cbo_permissions'
MARKER = 'data=0x43424f35'
MODES = [('M', 3 << 11, 11), ('HS', 1 << 11, 9), ('U', 0, 8),
         ('VS', (1 << 39) | (1 << 11), 10), ('VU', 1 << 39, 8)]
OPERATIONS = [('inval', 0, 4, (0, 1, 3)), ('clean', 1, 6, (0, 1)),
              ('flush', 2, 6, (0, 1)), ('zero', 4, 7, (0, 1))]
CSRS = ('menvcfg', 'henvcfg', 'senvcfg')


def cases():
    result = []
    for operation, funct12, shift, fields in OPERATIONS:
        for (mode, status, ecall), (m, h, s) in itertools.product(MODES, itertools.product(fields, repeat=3)):
            if mode == 'M':
                cause = 0
            elif not m or (mode == 'U' and not s):
                cause = 2
            elif (mode == 'VS' and not h) or (mode == 'VU' and not (h and s)):
                cause = 22
            else:
                cause = 0
            result.append(dict(operation=operation, mode=mode, status=status, ecall=ecall,
                               gates=[m << shift, h << shift, s << shift],
                               cause=cause, instruction=(funct12 << 20) | (11 << 15) | 0x200f))
    return result


def fixture(matrix):
    lines = [
        '.section .text.init,"ax"', '.option norvc', '.option norelax', '.globl _start',
        '_start:', 'la t0,trap', 'csrw mtvec,t0', 'csrw medeleg,zero', 'csrw mie,zero',
        'li t0,-1', 'csrw pmpaddr0,t0', 'li t0,31', 'csrw pmpcfg0,t0',
        'li s8,0x80070400', 'addi a1,s8,59', 'li s9,0x123456789abcdef0',
    ]
    for csr in CSRS:
        for legal in (0, 1, 3):
            lines += [f'li t0,{legal << 4}', f'csrw {csr},t0', 'li t1,0x20',
                      f'csrw {csr},t1', f'csrr t1,{csr}', 'bne t0,t1,fail']
    for index, case in enumerate(matrix):
        next_case = f'setup_{index + 1}' if index + 1 < len(matrix) else 'finish'
        lines += [
            f'setup_{index}:', f'li s0,{index + 1}', f'li s1,{case["cause"]}',
            f'li s2,{case["ecall"]}', f'li s3,{case["status"]}',
            f'la s4,probe_{index}', f'la s5,ecall_{index}', f'la s6,{next_case}',
            f'li a4,{case["instruction"]}', 'li s7,0', 'mv a5,s9', 'jal ra,fill',
        ]
        if case['operation'] == 'zero' and not case['cause']:
            lines += ['li a5,0']
        for csr, value in zip(CSRS, case['gates']):
            lines += [f'li t0,{value}', f'csrw {csr},t0', f'csrr t1,{csr}', 'bne t0,t1,fail']
        if case['mode'] != 'M':
            lines += ['csrw mstatus,s3', 'csrw mepc,s4', 'mret']
        lines += [f'probe_{index}:', f'.word {case["instruction"]}', f'ecall_{index}:', 'ecall', 'j fail']
    lines += [
        'fill:', 'addi t0,s8,-8', 'addi t1,s8,72',
        'fill_word:', 'sd s9,0(t0)', 'addi t0,t0,8', 'bne t0,t1,fill_word', 'ret',
        'trap:', 'csrr t0,mstatus', 'li t1,0x8000001800', 'and t0,t0,t1', 'bne t0,s3,fail',
        'csrr t0,mcause', 'beq t0,s2,done', 'beqz s1,fail', 'bne t0,s1,fail', 'bnez s7,fail',
        'csrr t0,mepc', 'bne t0,s4,fail', 'csrr t0,mtval', 'bne t0,a4,fail',
        'li s7,1', 'csrw mepc,s5', 'mret',
        'done:', 'csrr t0,mepc', 'bne t0,s5,fail', 'snez t0,s1', 'bne t0,s7,fail',
        'ld t0,-8(s8)', 'bne t0,s9,fail', 'ld t0,64(s8)', 'bne t0,s9,fail',
        'mv t0,s8', 'addi t1,s8,64', 'check_word:', 'ld t2,0(t0)', 'bne t2,a5,fail',
        'addi t0,t0,8', 'bne t0,t1,check_word', 'jr s6',
        'finish:', 'lui t0,0x10000', 'li t1,0x43424f35', 'sw t1,0xc(t0)',
        'sw zero,0x14(t0)', 'halt: j halt',
        'fail:', 'lui t0,0x10000', 'sw s0,0xc(t0)', 'li t1,1', 'sw t1,0x14(t0)', 'j halt',
    ]
    return '\n'.join(lines) + '\n'


def verify_trace(path, matrix):
    with path.open(newline='') as stream:
        rows = [row for row in csv.DictReader(stream) if int(row['pc'], 16) >= 0x80000000]
    probes = [row for row in rows if (int(row['instruction'], 16) & 0xfffff) == 0x5a00f]
    assert len(probes) == len(matrix), len(probes)
    for row, case in zip(probes, matrix):
        assert int(row['instruction'], 16) == case['instruction'], (row, case)
        assert (row['trap'] == '1') == bool(case['cause']), (row, case)
        if case['cause']:
            assert int(row['cause']) == case['cause'] and int(row['tval'], 16) == case['instruction'], (row, case)
    traps = [int(row['cause']) for row in rows if row['trap'] == '1']
    assert traps == [code for case in matrix for code in (case['cause'], case['ecall']) if code]
    return {str(cause): sum(case['cause'] == cause for case in matrix) for cause in (0, 2, 22)}


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source, elf, trace = (folder / name for name in ('test.S', 'test.elf', 'commit.csv'))
    matrix = cases()
    source.write_text(fixture(matrix), encoding='utf-8')
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    assert all(p in model['params'] for p in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1', '-GHAS_CBO=1'))
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

    fresh()
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh_zicbom_zicboz', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax','-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=2000000', '+expected_exit_code=0'], folder / 'simulation.log', 240)
    fresh()
    assert MARKER in log and 'PASS rv32_program_tb' in log
    outcomes = verify_trace(trace, matrix)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime, cases=matrix,
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=sha(elf),
        trace_sha256=sha(trace), compile=compile_run, run=run, outcomes=outcomes))
    print(f'PASS native CBO permissions: {len(matrix)} cases, outcomes {outcomes}', flush=True)


if __name__ == '__main__':
    main()


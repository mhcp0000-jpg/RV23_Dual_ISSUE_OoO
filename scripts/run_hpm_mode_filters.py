"""Exercise Sscofpmf retirement filtering and machine overflow on the H/V SoC."""

import argparse
import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


MODES = [
    ('M', 3 << 11, 62, 11),
    ('HS', 1 << 11, 61, 9),
    ('U', 0, 60, 8),
    ('VS', (1 << 39) | (1 << 11), 59, 10),
    ('VU', 1 << 39, 58, 8),
]
ALL_FILTERS = 0x1f << 58
DELTA = 10
MARKER = '0x48504d35'
OVERFLOW_MARKER = '0x48504d4f'
VISIBILITY_MARKER = '0x48504d56'
OVERFLOW_FLAGS = 0x58
VISIBILITY_MASKS = (0, 0x28, 0x50, 0x78)
VISIBILITY_MODES = (('M', 0, 0), ('HS', 1 << 11, 9), ('VS', (1 << 39) | (1 << 11), 10))


def fixture():
    lines = [
        '.section .text.init,"ax"', '.option norvc', '.option norelax',
        '.globl _start', '_start:', 'la t0,trap', 'csrw mtvec,t0',
        'li t0,-1', 'csrw pmpaddr0,t0', 'li t0,31', 'csrw pmpcfg0,t0',
        'li t0,0x18', 'csrw mcounteren,t0', 'csrw hcounteren,t0',
        'csrw scounteren,t0', 'csrw medeleg,zero', 'csrw mie,zero',
    ]
    for index, (mode, status, bit, cause) in enumerate(MODES):
        resume = f'setup_{index + 1}' if index + 1 < len(MODES) else 'finish'
        lines += [
            f'setup_{index}:', f'li s0,{index + 1}', f'li s1,{cause}',
            f'li s2,{status}', f'la s3,{resume}', f'la s4,ecall_{index}',
            'li t0,0x18', 'csrw mcountinhibit,t0',
            'csrw mhpmcounter3,zero', 'csrw mhpmcounter4,zero',
            f'li t0,{(ALL_FILTERS ^ (1 << bit)) | 2}', 'csrw mhpmevent3,t0',
            f'li t0,{(1 << bit) | 2}', 'csrw mhpmevent4,t0',
            'csrw mcountinhibit,zero',
        ]
        if mode != 'M':
            lines += [f'la t0,probe_{index}', 'csrw mepc,t0', 'csrw mstatus,s2', 'mret']
        lines += [
            f'probe_{index}:', 'csrr t0,hpmcounter3', 'csrr t1,hpmcounter4',
            *['addi t2,t2,1'] * 8,
            'csrr t3,hpmcounter3', 'csrr t4,hpmcounter4',
            'sub a0,t3,t0', 'sub a1,t4,t1',
            f'ecall_{index}:', 'ecall', 'j fail',
        ]
    lines += [
        'trap:', 'csrr t0,mcause', 'bne t0,s1,fail',
        'csrr t0,mepc', 'bne t0,s4,fail',
        'csrr t0,mstatus', 'li t1,0x8000001800', 'and t0,t0,t1', 'bne t0,s2,fail',
        f'li t0,{DELTA}', 'bne a0,t0,fail', 'bnez a1,fail', 'jr s3',
        'finish:', 'lui t0,0x10000', f'li t1,{MARKER}', 'sw t1,0xc(t0)',
        'sw zero,0x14(t0)', 'halt: j halt',
        'fail:', 'lui t0,0x10000', 'sw s0,0xc(t0)', 'sw a0,0xc(t0)',
        'sw a1,0xc(t0)', 'li t1,1', 'sw t1,0x14(t0)', 'j halt',
    ]
    return '\n'.join(lines) + '\n'


def trace_modes(trace):
    with trace.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    observed = []
    start = 0
    for index, row in enumerate(rows):
        if row['trap'] != '1' or int(row['pc'], 16) < 0x80000000:
            continue
        segment = rows[start:index]
        result = []
        for register in (10, 11):
            last = next(entry for entry in reversed(segment)
                        if entry['gpr_we'] == '1' and int(entry['rd']) == register)
            result.append(int(last['wdata'], 16))
        observed.append(dict(cause=int(row['cause']), included=result[0], excluded=result[1]))
        start = index + 1
    expected = [dict(cause=cause, included=DELTA, excluded=0) for _, _, _, cause in MODES]
    assert observed == expected, observed
    return [dict(mode=mode, **result) for (mode, *_), result in zip(MODES, observed)]



def overflow_fixture():
    return """.section .text.init,"ax"
.option norvc
.option norelax
.globl _start
_start:
  la t0,trap
  csrw mtvec,t0
  csrw mideleg,zero
  csrci mstatus,8
  li t0,0x2000
  csrw mie,t0
  li s0,1
  li s1,0
  csrw mip,zero
  li t0,8
  csrw mcountinhibit,t0
  csrwi mhpmevent3,1
  jal ra,wrap
  li t1,0x2000
  csrr t0,mip
  and t0,t0,t1
  bne t0,t1,fail
  li t1,8
  csrr t0,scountovf
  bne t0,t1,fail
  bnez s1,fail
  csrsi mstatus,8
first_irq:
  beqz s1,first_irq
  li t0,1
  bne s1,t0,fail

  # A hardware wrap with OF already set must preserve OF without a new IRQ.
  li s0,2
  jal ra,wrap
  li t1,0x2000
  csrr t0,mip
  and t0,t0,t1
  bnez t0,fail
  li t1,8
  csrr t0,scountovf
  bne t0,t1,fail
  li t0,1
  bne s1,t0,fail

  # Clear OF while inhibited, then allow hardware to overflow again.
  li s0,3
  csrwi mhpmevent3,1
  csrr t0,scountovf
  bnez t0,fail
  jal ra,wrap
  li t0,2
second_irq:
  bltu s1,t0,second_irq
  bne s1,t0,fail
  li t1,0x2000
  csrr t0,mip
  and t0,t0,t1
  bnez t0,fail
  li t1,8
  csrr t0,scountovf
  bne t0,t1,fail
  lui t0,0x10000
  li t1,0x48504d4f
  sw t1,0xc(t0)
  sw zero,0x14(t0)
halt: j halt

wrap:
  li t0,-1
  csrw mhpmcounter3,t0
  csrw mcountinhibit,zero
wait_wrap:
  csrr t0,mhpmcounter3
  bltz t0,wait_wrap
  li t0,8
  csrw mcountinhibit,t0
  ret

trap:
  beqz s0,fail
  li t4,2
  beq s0,t4,fail
  csrr t3,mcause
  li t4,0x800000000000000d
  bne t3,t4,fail
  csrr t3,mtval
  bnez t3,fail
  csrr t3,mstatus
  li t4,0x1800
  and t3,t3,t4
  bne t3,t4,fail
  csrr t3,scountovf
  li t4,8
  bne t3,t4,fail
  li t4,0x2000
  csrrc t3,mip,t4
  and t3,t3,t4
  bne t3,t4,fail
  addi s1,s1,1
  mret

fail:
  lui t0,0x10000
  sw s0,0xc(t0)
  sw s1,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j halt
"""


def trace_overflow(trace):
    traps = []
    phase = 0
    with trace.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row['gpr_we'] == '1' and int(row['rd']) == 8:
                phase = int(row['wdata'], 16)
            if row['trap'] == '1' and int(row['pc'], 16) >= 0x80000000:
                traps.append(dict(row, phase=phase))
    assert [(int(row['cause']), row['phase']) for row in traps] == [(13, 1), (13, 3)], traps
    assert all(int(row['tval'], 16) == 0 for row in traps), traps
    return traps


def visibility_cases():
    for mode, status, cause in VISIBILITY_MODES:
        for m_enable in VISIBILITY_MASKS:
            for h_enable in VISIBILITY_MASKS:
                mask = 0x78 if mode == 'M' else m_enable
                if mode == 'VS':
                    mask &= h_enable
                yield dict(mode=mode, status=status, cause=cause, m_enable=m_enable,
                           h_enable=h_enable, value=OVERFLOW_FLAGS & mask)


def visibility_fixture():
    lines = [
        '.section .text.init,"ax"', '.option norvc', '.option norelax',
        '.globl _start', '_start:', 'la t0,trap', 'csrw mtvec,t0',
        'li t0,-1', 'csrw pmpaddr0,t0', 'li t0,31', 'csrw pmpcfg0,t0',
        'csrw medeleg,zero', 'csrw mie,zero', 'csrw scounteren,zero',
        'li t0,0x78', 'csrw mcountinhibit,t0', 'li t0,-1',
        'csrw mhpmcounter3,t0', 'csrw mhpmcounter4,t0', 'csrw mhpmcounter6,t0',
        'li t0,0x8000000000000001',
        'csrw mhpmevent3,t0', 'csrw mhpmevent4,t0', 'csrw mhpmevent6,t0',
        'csrw mhpmevent31,t0', 'csrr t0,mip', 'li t1,0x2000',
        'and t0,t0,t1', 'bnez t0,fail',
    ]
    for index, case in enumerate(visibility_cases()):
        lines += [
            f'setup_{index}:', f'li s0,{index + 1}', f'li s1,{case["cause"]}',
            f'li t0,{case["m_enable"]}', 'csrw mcounteren,t0',
            f'li t0,{case["h_enable"]}', 'csrw hcounteren,t0',
        ]
        if case['mode'] != 'M':
            lines += [f'la t0,probe_{index}', 'csrw mepc,t0',
                      f'li t0,{case["status"]}', 'csrw mstatus,t0',
                      f'la s2,ecall_{index}', f'la s3,setup_{index + 1}', 'mret']
        lines += [f'probe_{index}:', 'csrr a0,scountovf',
                  f'li t0,{case["value"]}', 'bne a0,t0,fail']
        if case['mode'] != 'M':
            lines += [f'ecall_{index}:', 'ecall', 'j fail']
    lines += [
        f'setup_{index + 1}:', 'lui t0,0x10000', f'li t1,{VISIBILITY_MARKER}',
        'sw t1,0xc(t0)', 'sw zero,0x14(t0)', 'halt: j halt',
        'trap:', 'csrr t0,mcause', 'bne t0,s1,fail',
        'csrr t0,mepc', 'bne t0,s2,fail', 'jr s3',
        'fail:', 'lui t0,0x10000', 'sw s0,0xc(t0)', 'sw a0,0xc(t0)',
        'li t1,1', 'sw t1,0x14(t0)', 'j halt',
    ]
    return '\n'.join(lines) + '\n'


def trace_visibility(trace):
    cases = list(visibility_cases())
    observed = []
    traps = []
    with trace.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if int(row['pc'], 16) < 0x80000000:
                continue
            if row['trap'] == '1':
                assert int(row['instruction'], 16) == 0x73
                traps.append(int(row['cause']))
            elif int(row['instruction'], 16) == 0xda002573:  # csrr a0,scountovf
                assert row['gpr_we'] == '1' and int(row['rd']) == 10
                observed.append(int(row['wdata'], 16))
    assert observed == [case['value'] for case in cases], observed
    assert traps == [case['cause'] for case in cases if case['cause']], traps
    return dict(cases=cases, ecalls=len(traps))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--machine-overflow', action='store_true')
    group.add_argument('--overflow-visibility', action='store_true')
    args = parser.parse_args()
    if args.machine_overflow:
        name, build_fixture, marker = 'hpm_machine_overflow', overflow_fixture, OVERFLOW_MARKER
    elif args.overflow_visibility:
        name, build_fixture, marker = 'hpm_overflow_visibility', visibility_fixture, VISIBILITY_MARKER
    else:
        name, build_fixture, marker = 'hpm_mode_filters', fixture, MARKER
    folder = ROOT / 'out/rva23' / name
    folder.mkdir(parents=True, exist_ok=True)
    source, elf, trace = (folder / name for name in ('test.S', 'test.elf', 'commit.csv'))
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', 'tb/e2e/dpi/elf_loader.cpp',
    ]
    assert all(p in model['params'] for p in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'))
    runtime = source_inputs(['tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])

    def fresh():
        assert source_inputs(files) == model['inputs']
        assert sha(ROOT / model['binary']) == model['binary_sha256']
        for path, digest in runtime.items():
            assert sha(ROOT / path) == digest, path

    fresh()
    source.write_text(build_fixture(), encoding='utf-8')
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=1000000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    fresh()
    assert 'PASS rv32_program_tb' in log and f'data={marker}' in log
    if args.machine_overflow:
        evidence = {'traps': trace_overflow(trace)}
    elif args.overflow_visibility:
        evidence = {'visibility': trace_visibility(trace)}
    else:
        evidence = {'modes': trace_modes(trace)}
    dump(folder / 'report.json', dict(
        passed=True, model=model, runtime_inputs=runtime, generator_sha256=sha(__file__),
        source_sha256=sha(source), elf_sha256=sha(elf), trace_sha256=sha(trace),
        compile=compile_run, run=run, **evidence))
    print('PASS native HPM:', name, flush=True)


if __name__ == '__main__':
    main()


"""Audit VLEN128/ELEN64 vector configuration, AVL and keep-vl behavior."""

from run_sail_event_comparison import compare, read_csv
from run_hv_sail_fixture import run_fixture
from sim_runner import ROOT


FOLDER = 'out/rva23/vector_config_contract'
VILL = 1 << 63
MAX_AVL = (1 << 64) - 1


def register_cases():
    capacities = {}
    # V requires integral LMULs and fractional LMULs through SEW <= LMUL*ELEN.
    for width, min_lmul in enumerate((-3, -2, -1, 0)):
        for lmul in range(min_lmul, 4):
            for policy in range(4):
                vtype = (policy << 6) | (width << 3) | (lmul & 7)
                capacities[vtype] = 1 << (4 + lmul - width)
    for vtype in range(256):
        limit = capacities.get(vtype)
        if limit is None:
            yield vtype, 7, 0, VILL
        else:
            for avl in (0, 1, limit - 1, limit, limit + 1, 2 * limit - 1, 2 * limit, MAX_AVL):
                yield vtype, avl, min(avl, limit), vtype
    for bit in range(8, 64):
        yield 1 << bit, 7, 0, VILL


# Instructions in order, type/AVL operand setup, and expected CSR values.
TRANSITIONS = [
    ('vsetivli a0,13,e8,m1,ta,ma', (), 13, 0xc0),
    ('vsetvli zero,zero,e16,m2,tu,mu', (), 13, 0x09),
    ('vsetvl zero,zero,a2', ('li a2,0x12',), 13, 0x12),
    ('vsetvli zero,zero,e16,m1,tu,mu', (), 0, VILL),
    ('vsetvl zero,zero,a2', ('li a2,0x08',), 0, VILL),
    ('vsetvl a0,zero,a2', ('li a2,0x12',), 16, 0x12),
    ('vsetvl zero,zero,a2', ('li a2,0x03',), 0, VILL),
    ('vsetvli a0,zero,e8,m8,tu,mu', (), 128, 0x03),
    ('vsetivli zero,31,e64,m1,tu,mu', (), 2, 0x18),
    ('.word 0x1005f557', ('li a1,2',), 0, VILL),  # vsetvli with reserved vtype[8]
    ('.word 0xd0017557', (), 0, VILL),            # vsetivli with reserved vtype[8]
    ('vsetvl a1,a1,a2', ('li a1,3', 'li a2,0x09'), 3, 0x09),
    ('vsetvl a2,a1,a2', ('li a1,4', 'li a2,0x12'), 4, 0x12),
]


def fixture():
    cases = list(register_cases())
    lines = [
        '.section .text.init,"ax"', '.option norvc', '.option norelax',
        '.globl _start', '_start:', 'la t0,fail', 'csrw mtvec,t0',
        'li t0,0x600', 'csrs mstatus,t0', 'la s0,cases', f'li s1,{len(cases)}',
        'loop:', 'ld a2,0(s0)', 'ld a1,8(s0)', 'ld a3,16(s0)', 'ld a4,24(s0)',
        'csrwi vstart,1', 'vsetvl a0,a1,a2', 'jal ra,check_config',
        'addi s0,s0,32', 'addi s1,s1,-1', 'bnez s1,loop',
    ]
    for instruction, setup, expected_vl, expected_vtype in TRANSITIONS:
        lines.extend(setup)
        lines += [f'li a3,{expected_vl}', f'li a4,{expected_vtype}', 'csrwi vstart,1', instruction]
        if instruction.split()[1].startswith('zero,'):
            lines.append('mv a0,a3')  # These forms have no scalar destination.
        elif instruction.startswith(('vsetvl a1,', 'vsetvl a2,')):
            lines.append('mv a0,' + instruction.split()[1].split(',')[0])
        lines.append('jal ra,check_config')
    lines += [
        'li t1,1', 'j finish',
        'check_config:', 'bne a0,a3,fail', 'csrr t0,vtype', 'bne t0,a4,fail',
        'csrr t1,vl', 'bne t1,a3,fail', 'csrr t2,vstart', 'bnez t2,fail', 'ret',
        'fail:', 'li t1,3', 'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0', '.section .rodata', '.balign 8', 'cases:',
    ]
    lines.extend('.dword ' + ','.join(str(field) for field in case) for case in cases)
    return '\n'.join(lines) + '\n'


def verify_traces(sail_trace, rtl_trace):
    actual = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), actual)
    assert mismatch is None, mismatch
    observed = []
    reads = {0xc21022f3: 'vtype', 0xc2002373: 'vl', 0x008023f3: 'vstart'}
    for row in actual:
        if int(row['pc'], 16) < 0x80000000:
            continue
        assert row['trap'] == '0', row
        field = reads.get(int(row['instruction'], 16))
        if field:
            assert row['rd_write'] == '1'
            observed.append((field, int(row['wdata'], 16)))
    cases = list(register_cases())
    configurations = [(vl, vtype) for _, _, vl, vtype in cases]
    configurations.extend((vl, vtype) for _, _, vl, vtype in TRANSITIONS)
    assert observed == [read for vl, vtype in configurations
                        for read in [('vtype', vtype), ('vl', vl), ('vstart', 0)]]
    return dict(register_cases=len(cases), transitions=len(TRANSITIONS),
                vill_outcomes=sum(vtype == VILL for _, vtype in configurations), matched_events=events)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'test.S'
    source.write_text(fixture(), encoding='utf-8')
    outcomes = run_fixture(source, folder, __file__, verify_traces, timeout_cycles=1500000)
    print('PASS RVV vector configuration', outcomes, flush=True)


if __name__ == '__main__':
    main()

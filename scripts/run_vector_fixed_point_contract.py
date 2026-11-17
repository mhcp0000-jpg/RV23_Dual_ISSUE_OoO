"""Compare fixed-point rounding and saturation state across inactive RVV lanes."""

from itertools import product

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT


FOLDER = 'out/rva23/vector_fixed_point_contract'
LANE_SELECTIONS = (
    ('all', 4, 0, 0xf, 0),
    ('masked', 4, 0, 0xe, 0),
    ('restart', 4, 1, 0xf, 0),
    ('tail', 3, 0, 0xf, 0),
    ('zero_length', 0, 0, 0xf, 0),
    ('completed', 2, 2, 0xf, 0),
    ('sticky', 4, 1, 0xf, 1),
)


def operands():
    for width in (8, 16, 32, 64):
        bound = 1 << (width - 1)
        for scalar in (-bound, -(bound // 2)):
            yield 'vsmul', width, [-bound, 3, -3, bound - 1], scalar
        if width < 64:
            yield 'vnclip', width, [2 * bound, 3, -3, -5], 0
            yield 'vnclip', width, [-2 * bound - 2, -7, 3, 5], 0


def rounded(value, shift, mode):
    unit = 1 << shift
    integer, fraction = divmod(value, unit)
    increments = (
        2 * fraction >= unit,
        2 * fraction > unit or (2 * fraction == unit and integer % 2 == 1),
        False,
        fraction != 0 and integer % 2 == 0,
    )
    return integer + increments[mode]


def cases():
    for (op, width, inputs, scalar), mode, (selection, vl, start, mask, sticky) in product(
            operands(), range(4), LANE_SELECTIONS):
        bound = 1 << (width - 1)
        if selection == 'tail':
            inputs = inputs[1:] + inputs[:1]
        expected = [7] * 4
        saturated = sticky
        for lane in range(start, vl):
            if not mask & (1 << lane):
                continue
            value = rounded(inputs[lane] * scalar, width - 1, mode) if op == 'vsmul' else rounded(
                inputs[lane], 1, mode)
            clipped = min(bound - 1, max(-bound, value))
            expected[lane] = clipped & ((1 << width) - 1)
            saturated |= int(value != clipped)
        yield dict(op=op, width=width, inputs=inputs, scalar=scalar, mode=mode, selection=selection,
                   vl=vl, start=start, mask=mask, sticky=sticky, expected=expected, saturated=saturated)


def fixture():
    lines = [
        '.section .text.init,"ax"', '.option norvc', '.option norelax',
        '.globl _start', '_start:', 'la t0,fail', 'csrw mtvec,t0',
        'li t0,0x600', 'csrs mstatus,t0',
    ]
    data = []
    load_mnemonics = {8: 'lbu', 16: 'lhu', 32: 'lwu', 64: 'ld'}
    for index, case in enumerate(cases()):
        op, width, mode = case['op'], case['width'], case['mode']
        source_bytes = width // (8 if op == 'vsmul' else 4)
        packed = b''.join(value.to_bytes(source_bytes, 'little', signed=True) for value in case['inputs'])
        data += [f'input_{index}:', '.byte ' + ','.join(map(str, packed.ljust(64, b'\0')))]
        instruction = 'vsmul.vx v16,v8,t3,v0.t' if op == 'vsmul' else 'vnclip.wi v16,v8,1,v0.t'
        lines += [
            f'la t0,input_{index}', 'vl4re8.v v8,(t0)',
            f'vsetivli zero,4,e{width},m2,tu,mu', 'vmv.v.i v16,7',
            f'li t0,{case["mask"]}', 'vmv.s.x v0,t0',
            f'csrwi vcsr,{(mode << 1) | case["sticky"]}',
            f'li t3,{case["scalar"]}', f'vsetivli zero,{case["vl"]},e{width},m2,tu,mu',
            f'csrwi vstart,{case["start"]}', instruction,
            'csrr a0,vxsat', f'li a1,{case["saturated"]}', 'bne a0,a1,fail',
            'csrr a0,vcsr', f'li a1,{(mode << 1) | case["saturated"]}', 'bne a0,a1,fail',
            'csrr a0,vstart', 'bnez a0,fail', 'la t0,observed', 'vs2r.v v16,(t0)',
        ]
        for lane, value in enumerate(case['expected']):
            lines += [f'{load_mnemonics[width]} a0,{lane * (width // 8)}(t0)', f'li a1,{value}', 'bne a0,a1,fail']
    lines += [
        'li t1,1', 'j finish', 'fail:', 'li t1,3',
        'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0', '.section .bss', '.balign 16', 'observed:.space 32',
        '.section .rodata', '.balign 16', *data,
    ]
    return '\n'.join(lines) + '\n'


def verify_traces(sail_trace, rtl_trace):
    rtl = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), rtl)
    assert mismatch is None, mismatch
    csr_reads = (0x00902573, 0x00f02573, 0x00802573)
    csrs = []
    for row in rtl:
        if int(row['pc'], 16) < 0x80000000:
            continue
        assert row['trap'] == '0', row
        word = int(row['instruction'], 16)
        if word in csr_reads:
            assert row['rd_write'] == '1'
            csrs.append((word, int(row['wdata'], 16)))
    trials = list(cases())
    assert csrs == [item for trial in trials for item in (
        (csr_reads[0], trial['saturated']),
        (csr_reads[1], trial['mode'] << 1 | trial['saturated']),
        (csr_reads[2], 0),
    )]
    return dict(cases=len(trials), destination_elements=4 * len(trials), matched_events=events)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'test.S'
    source.write_text(fixture(), encoding='utf-8')
    results = run_fixture(source, folder, __file__, verify_traces, timeout_cycles=1500000)
    print('PASS vector fixed-point contract', results, flush=True)


if __name__ == '__main__':
    main()

"""Compare each Zvbb form on Sail and the RV64 SoC with full register readback."""
import json
from itertools import product

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT
from vector_integer_reference import calculate


FOLDER = 'out/rva23/zvbb_native'
TABLE = 'config/vector_opcode_tables/encodings.json'
ORACLE = 'scripts/vector_integer_reference.py'
MODES = ('full', 'masked_restart', 'zero_vl')
INITIAL = bytes([0xa5]) * 64
CONFIGURATIONS = {
    8: (('m2', 4), ('mf2', 4), ('mf4', 4), ('mf8', 2)),
    16: (('m2', 4), ('mf2', 4), ('mf4', 2)),
    32: (('m2', 4), ('mf2', 2)),
    64: (('m2', 4),),
}


def fixture():
    table = json.loads((ROOT / TABLE).read_text(encoding='utf-8'))
    forms = [entry['name'] for entry in table['instructions'] if entry['extension'] == 'ZVBB']
    assert len(forms) == len(set(forms)) == 16
    lines = ['.section .text.init,"ax"', '.option norvc', '.option norelax', '.option arch,+zvbb', '.globl _start',
             '_start:', 'la t0,fail', 'csrw mtvec,t0', 'li t0,0x600', 'csrs mstatus,t0',
             'la t0,mask_data', 'vl1re8.v v0,(t0)']
    data = ['.section .data,"aw"', '.balign 16', 'mask_data: .byte 2', '.zero 15',
            'initial: .fill 64,1,0xa5']
    cases = []
    for width, configs in CONFIGURATIONS.items():
        lane_bytes = width // 8
        bitmask = (1 << width) - 1
        source = [0, 0x81c1a50789abcdef & bitmask, 1 << (width - 1), bitmask]
        counts = [0, width + 3, width - 1, 2 * width - 1]
        for name, values in [('a', source), ('b', counts)]:
            packed = b''.join((value & bitmask).to_bytes(lane_bytes, 'little') for value in values)
            data += [f'{name}_{width}: .byte ' + ','.join(map(str, packed.ljust(32, b'\0')))]
        lines += [f'la t0,a_{width}', 'vl2re64.v v16,(t0)', f'la t0,b_{width}', 'vl2re64.v v24,(t0)']
        for form in forms:
            operation, operand_form = form.split('.')
            widening = operation == 'vwsll'
            if widening and width == 64:
                continue
            operand = {'v': '', 'vv': ',v24', 'vx': ',a0',
                       'vi': ',63' if operation == 'vror' else ',31'}[operand_form]
            b = {'v': [0] * 4, 'vv': counts, 'vx': [width + 1] * 4,
                 'vi': [63 if operation == 'vror' else 31] * 4}[operand_form]
            output_bytes = lane_bytes * (2 if widening else 1)
            for (lmul, full_vl), mode in product(configs, MODES):
                vl = {'full': full_vl, 'masked_restart': min(3, full_vl), 'zero_vl': 0}[mode]
                active = {'full': range(full_vl), 'masked_restart': (1,), 'zero_vl': ()}[mode]
                index = len(cases)
                snapshot = bytearray(INITIAL)
                for lane in active:
                    result, _, supported = calculate(operation, width, source[lane], b[lane], 0, 0, 0, 0, 0)
                    assert supported
                    offset = lane * output_bytes
                    snapshot[offset:offset + output_bytes] = result.to_bytes(output_bytes, 'little')
                words = [int.from_bytes(snapshot[i:i+8], 'little') for i in range(0, 64, 8)]
                cases.append(dict(form=form, width=width, lmul=lmul, mode=mode, words=words))
                data.append(f'expected_{index}: .dword ' + ','.join(f'{word:#x}' for word in words))
                lines += [f'li s0,{index}', 'la t0,initial', 'vl4re64.v v8,(t0)',
                          f'vsetivli zero,{vl},e{width},{lmul},tu,mu', f'li a0,{width + 1}']
                if mode == 'masked_restart':
                    lines += ['csrwi vstart,1']
                suffix = ',v0.t' if mode == 'masked_restart' else ''
                lines += [f'case_{index}: {form} v8,v16{operand}{suffix}', 'csrr a4,vstart',
                          'bnez a4,fail', 'la t0,snapshot', 'vs4r.v v8,(t0)',
                          f'la a2,expected_{index}', 'jal ra,check_words']
    lines += ['li t1,1', 'j finish',
              'check_words:', 'addi t2,t0,64', 'next_word:', 'ld a5,0(t0)', 'ld t1,0(a2)',
              'bne a5,t1,fail', 'addi t0,t0,8', 'addi a2,a2,8', 'bltu t0,t2,next_word', 'ret',
              'fail:', 'slli t1,s0,1', 'addi t1,t1,3',
              'finish: la t0,tohost', 'sd t1,0(t0)', 'halt: j halt',
              '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
              'tohost: .dword 0', 'fromhost: .dword 0',
              *data, '.section .bss,"aw",@nobits', '.balign 16', 'snapshot: .space 64']
    return '\n'.join(lines) + '\n', cases


def verify_traces(sail_trace, rtl_trace, cases):
    rtl = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), rtl)
    assert mismatch is None, mismatch
    rows = [row for row in rtl if int(row['pc'], 16) >= 0x80000000]
    assert all(row['trap'] == '0' for row in rows)
    expected_words = [word for case in cases for word in case['words']]
    assert [int(row['wdata'], 16) for row in rows
            if int(row['instruction'], 16) & 0x000fffff == 0x0002b783] == expected_words
    resets = [int(row['wdata'], 16) for row in rows if row['instruction'] == '00802773']
    assert resets == [0] * len(cases)
    return dict(forms=len({case['form'] for case in cases}), cases=len(cases),
                destination_words=len(expected_words), matched_events=events,
                fractional_lmul_cases=sum(case['lmul'].startswith('mf') for case in cases))


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'test.S'
    code, cases = fixture()
    source.write_text(code, encoding='utf-8')
    outcomes = run_fixture(source, folder, __file__,
                           lambda sail, rtl: verify_traces(sail, rtl, cases),
                           source_dependencies=(TABLE, ORACLE), timeout_cycles=2500000)
    print('PASS Sail/RTL Zvbb', outcomes, flush=True)


if __name__ == '__main__':
    main()

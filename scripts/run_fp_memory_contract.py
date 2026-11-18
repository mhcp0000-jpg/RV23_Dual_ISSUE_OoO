"""Native H/V FP memory/raw-half moves with an independent ELF byte model."""
import argparse
import copy
import json

from audit_hv_sail_fixture import check_fixture
from audit_rv64i_compute_control import sx
from audit_rv64i_memory_values import LOADS, STORES, initial_memory
from run_fp_integer_contract import labels
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/fp_memory_contract'
MASK = (1 << 64) - 1
GUARD = 0xa5a5a5a5a5a5a5a5
OFFSETS = (0, 1, 2, 7, 8, 60, 63, 4095)
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/audit_rv64i_memory_values.py',
    'scripts/run_fp_integer_contract.py', 'scripts/run_fp_bit_contract.py',
    'scripts/audit_rv64i_compute_control.py', 'scripts/audit_rv64m_contract.py', 'scripts/fp_reference.py']


def patterns(width):
    return {16: [0x7c01, 0x7e55, 0xfc01, 0x8000, 0, 0x3c00, MASK, 0x123456789abcbeef],
        32: [0x7f800123, 0x7fc01234, 0xff800123, 0x80000000, 0, 0x3f800000, MASK, 0x1234567889abcdef],
        64: [0x7ff0000000000123, 0x7ff8000000001234, 0xfff0000000000123,
            0x8000000000000000, 0, 0x3ff0000000000000, MASK, 0x1234567889abcdef]}[width]


def cases(width):
    code = {16: 1, 32: 2, 64: 3}[width]
    suffix = {16: 'h', 32: 'w', 64: 'd'}[width]
    forms = [(f'fl{suffix}', 'load', 18, False, 18 << 15 | code << 12 | 8 << 7 | 7),
             (f'fs{suffix}', 'store', 18, False, 8 << 20 | 18 << 15 | code << 12 | 0x27)]
    if width == 64:
        forms += [('c_fld', 'load', 9, True, 0x2080), ('c_fsd', 'store', 9, True, 0xa080),
                  ('c_fldsp', 'load', 2, True, 0x2402), ('c_fsdsp', 'store', 2, True, 0xa022)]
    result = []
    for name, kind, base, short, word in forms:
        for a in patterns(width):
            for offset in OFFSETS:
                result.append(dict(name=name, kind=kind, width=width, a=a,
                    address=0x80080000 + offset, base=base, short=short, word=word,
                    fflags=(0, 5, 31)[len(result) % 3]))
    if width == 16:
        for name, kind, word in [('fmv_h_x', 'tofp', 0xf4028453), ('fmv_x_h', 'toint', 0xe4040553)]:
            for a in patterns(width):
                for flags in (0, 5, 31):
                    result.append(dict(name=name, kind=kind, width=width, a=a,
                        word=word, short=False, fflags=flags))
    return result


def boxed(value, width):
    return value & ((1 << width) - 1) | (MASK ^ ((1 << width) - 1))


def fixture(width):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6000', 'csrs mstatus,t0']
    for index, case in enumerate(cases(width), 1):
        kind, a = case['kind'], case['a']
        lines += [f'li s0,{index}']
        if kind in ('load', 'store'):
            address = case['address']
            guard = (address & ~7) - 8
            lines += [f'li s2,{address:#x}', f'li s3,{guard:#x}', f'li t1,{GUARD:#x}',
                'sd t1,0(s3)', 'sd t1,8(s3)', 'sd t1,16(s3)', 'sd t1,24(s3)',
                'mv s1,s2', 'mv sp,s2']
            if kind == 'load':
                lines.append(f'li t0,{a:#x}')
                for offset in range(width // 8):
                    lines += [f'sb t0,{offset}(s2)', 'srli t0,t0,8']
        preload = a ^ MASK if kind == 'load' else a
        lines += [f'li t0,{preload:#x}', 'fmv.d.x fs0,t0', f'csrwi fflags,{case["fflags"]}',
            f'probe_{index}: {".2byte" if case["short"] else ".word"} {case["word"]:#x} # {case["name"]}']
        if kind != 'store':
            if kind != 'toint':
                lines.append('fmv.x.d a0,fs0')
            value = sx(a, 16) & MASK if kind == 'toint' else boxed(a, width)
            lines += [f'li t2,{value:#x}', 'bne a0,t2,fail']
        else:
            lines += ['fmv.x.d a0,fs0', f'li t2,{a:#x}', 'bne a0,t2,fail']
        if kind in ('load', 'store'):
            data = bytearray([0xa5] * 32)
            start = case['address'] - guard
            data[start:start + width // 8] = (a & ((1 << width) - 1)).to_bytes(width // 8, 'little')
            lines.append(f'li t1,{GUARD:#x}')
            for offset in range(0, 32, 8):
                value = int.from_bytes(data[offset:offset + 8], 'little')
                lines.append(f'ld t0,{offset}(s3)')
                if value == GUARD:
                    lines.append('bne t0,t1,fail')
                else:
                    lines += [f'li t2,{value:#x}', 'bne t0,t2,fail']
        lines += [f'flags_{index}: csrr a1,fflags', f'li t2,{case["fflags"]}', 'bne a1,t2,fail']
    lines += ['li t1,1', 'j finish', 'fail:', 'slli t1,s0,1', 'ori t1,t1,1',
        'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt: j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, width, symbols, initial):
    plan = cases(width)
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    flags = {symbols[f'flags_{i}']: case['fflags'] for i, case in enumerate(plan, 1)}
    registers, fp, memory = [None] * 32, [None] * 32, initial.copy()
    registers[0] = 0
    counts, seen, flag_reads, writes, writers = {}, set(), set(), {}, {}
    misaligned, line_crossings, page_crossings = 0, 0, 0

    def read(address, size):
        addresses = [address + i for i in range(size)]
        assert all(byte in memory for byte in addresses), (hex(address), size)
        for byte in addresses:
            if byte in writers:
                writes[writers[byte]]['observed'].add(byte)
        return sum(memory[byte] << (8 * i) for i, byte in enumerate(addresses))

    def write(address, size, value, owner=None):
        for i in range(size):
            byte = address + i
            memory[byte] = (value >> (8 * i)) & 255
            if owner is None:
                writers.pop(byte, None)
            else:
                writers[byte] = owner

    for index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if pc >= 0x80000000:
            assert row['trap'] == '0', row
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and word == case['word'], row
            seen.add(pc)
            counts[case['name']] = counts.get(case['name'], 0) + 1
            kind = case['kind']
            if kind in ('load', 'store'):
                address, size = registers[case['base']], width // 8
                assert address == case['address']
                misaligned += address % size != 0
                line_crossings += address // 64 != (address + size - 1) // 64
                page_crossings += address // 4096 != (address + size - 1) // 4096
                if kind == 'load':
                    assert fp[8] == case['a'] ^ MASK
                    value = boxed(read(address, size), width)
                else:
                    assert fp[8] == case['a'] and row['rd_write'] == '0', row
                    writes[index] = dict(addresses=set(range(address, address + size)), observed=set())
                    write(address, size, fp[8], index)
            elif kind == 'tofp':
                assert registers[5] == case['a']
                value = boxed(registers[5], 16)
            else:
                assert kind == 'toint' and fp[8] == case['a']
                value = sx(fp[8], 16) & MASK
            if kind != 'store':
                assert row['rd_write'] == '1' and int(row['rd_fp']) == (kind != 'toint')
                assert int(row['rd']) == (10 if kind == 'toint' else 8)
                assert int(row['wdata'], 16) == value, (case, row)
        elif pc >= 0x80000000 and word & 127 in (3, 0x23):
            opcode, f3 = word & 127, (word >> 12) & 7
            load = opcode == 3
            base = registers[(word >> 15) & 31]
            assert base is not None
            immediate = word >> 20 if load else (word >> 25) << 5 | (word >> 7) & 31
            address = (base + sx(immediate, 12)) & MASK
            if load:
                assert f3 in LOADS
                _, size, sign = LOADS[f3]
                value = read(address, size)
                value = (sx(value, 8 * size) if sign else value) & MASK
                rd = (word >> 7) & 31
                if rd:
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                    assert int(row['wdata'], 16) == value, row
            else:
                assert f3 in STORES
                _, size = STORES[f3]
                value = registers[(word >> 20) & 31]
                assert value is not None
                write(address, size, value)
        if pc in flags:
            assert pc not in flag_reads and word == 0x001025f3
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '11'
            assert int(row['wdata'], 16) == flags[pc]
            flag_reads.add(pc)
        if row['trap'] == '0' and row['rd_write'] == '1':
            rd, value = int(row['rd']), int(row['wdata'], 16)
            if row['rd_fp'] == '1':
                fp[rd] = value
            elif rd:
                registers[rd] = value
    assert len(seen) == len(flag_reads) == len(plan)
    assert all(value['observed'] == value['addresses'] for value in writes.values())
    return dict(probes=len(plan), forms=counts, checked_fflags_reads=len(flag_reads),
        misaligned_accesses=misaligned, line_crossings=line_crossings, page_crossings=page_crossings,
        fully_observed_fp_stores=len(writes))


def verifier(width, folder):
    def verify(sail_trace, rtl_trace):
        actual = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), actual)
        assert mismatch is None, mismatch
        symbols, initial = labels(folder), initial_memory(folder / 'test.elf')
        result = inspect(actual, width, symbols, initial)
        controls = []
        for name in result['forms']:
            index, case = next((i, case) for i, case in enumerate(cases(width), 1) if case['name'] == name)
            for kind in ('value', 'fflags'):
                broken = copy.deepcopy(actual)
                pc = symbols[f'{"probe" if kind == "value" else "flags"}_{index}']
                target = next(i for i, row in enumerate(broken) if int(row['pc'], 16) == pc)
                if kind == 'value' and case['kind'] == 'store':
                    target = next(i for i in range(target + 1, len(broken))
                        if int(broken[i]['instruction'], 16) & 127 == 3 and broken[i]['rd_write'] == '1')
                row = broken[target]
                row['wdata'] = f"{int(row['wdata'], 16) ^ (1 if kind == 'value' else 16):016x}"
                try:
                    inspect(broken, width, symbols, initial)
                except AssertionError:
                    controls.append(dict(name=name, kind=kind))
                else:
                    raise AssertionError(f'Incorrect {name} {kind} accepted')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='Finite bare-mode H/S/D byte values, guard preservation, C D memory and raw H moves; bus atomicity/order, faults and FS/pipeline races separate',
        inputs=source_inputs(DEPENDENCIES), cases=[])
    if args.check:
        saved = json.loads((FOLDER / 'report.json').read_bytes())
        assert saved['passed'] and saved['generator_sha256'] == top['generator_sha256']
        assert saved['inputs'] == top['inputs'] and len(saved['cases']) == 3
    else:
        dump(FOLDER / 'report.json', top)
    for width in (16, 32, 64):
        folder = FOLDER / str(width)
        folder.mkdir(exist_ok=True)
        source, verify = folder / 'test.S', verifier(width, folder)
        if args.check:
            outcomes = check_fixture(folder, __file__, fixture(width), verify)
            old = next(case for case in saved['cases'] if case['width'] == width)
            assert old['report_sha256'] == sha(folder / 'report.json') and old['outcomes'] == outcomes
        else:
            source.write_text(fixture(width), encoding='utf-8')
            outcomes = run_fixture(source, folder, __file__, verify,
                source_dependencies=DEPENDENCIES, timeout_cycles=2000000)
        top['cases'].append(dict(width=width, report_sha256=sha(folder / 'report.json'), outcomes=outcomes))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS native FP memory', width, outcomes['probes'], 'probes;',
              outcomes['matched_events'], 'Sail/RTL events;', len(outcomes['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

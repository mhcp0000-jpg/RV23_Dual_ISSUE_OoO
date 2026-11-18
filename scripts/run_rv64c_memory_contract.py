"""Native compressed W/D and FP D memory field sweep with ELF-backed bytes."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from audit_rv64i_compute_control import sx
from audit_rv64i_memory_values import LOADS, STORES, initial_memory
from audit_rv64m_contract import MASK
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/rv64c_memory_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/audit_rv64i_compute_control.py',
    'scripts/audit_rv64i_memory_values.py', 'scripts/audit_rv64m_contract.py']
PATTERNS = [0, MASK, 0x80000000, 0x7fffffff, 0x1234567889abcdef,
            0x7ff0000000000123, 0x7ff8000000001234, 1 << 63]
FORMS = ['lw', 'ld', 'sw', 'sd', 'fld', 'fsd', 'lwsp', 'ldsp', 'swsp', 'sdsp', 'fldsp', 'fsdsp']
GUARD = 0xa5a5a5a5a5a5a5a5
BATCH = 200


def attributes(name):
    return name.startswith(('l', 'fl')), name.startswith('f'), (4 if 'w' in name else 8), name.endswith('sp')


def encode(case):
    name, base, other, offset = (case[key] for key in ('name', 'base', 'other', 'offset'))
    load, fp, size, stack = attributes(name)
    f3 = (1 if fp else 2 if size == 4 else 3) + (0 if load else 4)
    word = f3 << 13 | (2 if stack else 0)
    if not stack:
        word |= (base - 8) << 7 | (other - 8) << 2 | ((offset >> 3) & 7) << 10
        word |= (((offset >> 6) & 3) << 5) if size == 8 else (
            ((offset >> 6) & 1) << 5 | ((offset >> 2) & 1) << 6)
    elif load:
        word |= other << 7 | ((offset >> 5) & 1) << 12
        word |= (((offset >> 6) & 7) << 2 | ((offset >> 3) & 3) << 5) if size == 8 else (
            ((offset >> 6) & 3) << 2 | ((offset >> 2) & 7) << 4)
    else:
        word |= other << 2
        word |= (((offset >> 6) & 7) << 7 | ((offset >> 3) & 7) << 10) if size == 8 else (
            ((offset >> 6) & 3) << 7 | ((offset >> 2) & 15) << 9)
    return word


def decode(word):
    q, f3 = word & 3, (word >> 13) & 7
    assert q in (0, 2) and f3 in (1, 2, 3, 5, 6, 7)
    load, fp, size = f3 < 4, f3 in (1, 5), 4 if f3 in (2, 6) else 8
    if q == 0:
        base, other = 8 + ((word >> 7) & 7), 8 + ((word >> 2) & 7)
        offset = ((word >> 10) & 7) << 3
        offset |= (((word >> 5) & 3) << 6) if size == 8 else (
            ((word >> 5) & 1) << 6 | ((word >> 6) & 1) << 2)
    else:
        base, other = 2, ((word >> 7) & 31) if load else ((word >> 2) & 31)
        assert not load or fp or other != 0
        if load:
            offset = ((word >> 12) & 1) << 5
            offset |= (((word >> 2) & 7) << 6 | ((word >> 5) & 3) << 3) if size == 8 else (
                ((word >> 2) & 3) << 6 | ((word >> 4) & 7) << 2)
        else:
            offset = (((word >> 7) & 7) << 6 | ((word >> 10) & 7) << 3) if size == 8 else (
                ((word >> 7) & 3) << 6 | ((word >> 9) & 15) << 2)
    name = ('f' if fp else '') + ('l' if load else 's') + ('w' if size == 4 else 'd') + ('sp' if q == 2 else '')
    return name, load, fp, size, base, other, offset


def cases():
    plan = []
    def add(name, base, other, offset, address, a):
        load, fp, size, _ = attributes(name)
        if not load and not fp:
            a = 0 if other == 0 else address - offset if other == base else a
        plan.append(dict(name=name, base=base, other=other, offset=offset,
            address=address, a=a, fflags=(0, 5, 31)[len(plan) % 3]))
    for name in FORMS:
        load, fp, size, stack = attributes(name)
        for index in range(64 if stack else 32):
            for variant in range(2 if stack else 8):
                base = 2 if stack else 8 + variant
                other = ((index + variant * 17) % 32 if fp or not load else
                         1 + (index + variant * 17) % 31) if stack else 8 + (index + variant) % 8
                add(name, base, other, index * size, 0x80090000 + (index * size) % 128,
                    PATTERNS[(index + variant) % len(PATTERNS)])
        for index, crossing in enumerate((1, 2, 7, 60, 63, 4095)):
            for variant in range(2):
                add(name, 2 if stack else 9, (0 if fp else 2) if stack else 9,
                    (index + 1) * size, 0x80090000 + crossing, PATTERNS[4 + variant])
    return plan


def roles(case):
    return [reg for reg in range(16, 24) if reg not in (case['base'], case['other'])][:4]


def expected(case):
    _, fp, size, _ = attributes(case['name'])
    raw = case['a'] & ((1 << (8 * size)) - 1)
    return (sx(raw, 32) if not fp and size == 4 else raw) & MASK


def fixture(plan):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6000', 'csrs mstatus,t0']
    for index, case in enumerate(plan, 1):
        load, fp, size, _ = attributes(case['name'])
        addr, guard, scratch, check = roles(case)
        address, other, base, a = (case[key] for key in ('address', 'other', 'base', 'a'))
        guard_address = (address & ~7) - 8
        lines += [f'li x{addr},{address:#x}', f'li x{guard},{guard_address:#x}', f'li x{scratch},{GUARD:#x}']
        lines += [f'sd x{scratch},{offset}(x{guard})' for offset in range(0, 32, 8)]
        if load:
            lines.append(f'li x{scratch},{a:#x}')
            for offset in range(size):
                lines += [f'sb x{scratch},{offset}(x{addr})', f'srli x{scratch},x{scratch},8']
        preload = (expected(case) ^ MASK) if load else a
        if fp:
            lines += [f'li x{scratch},{preload:#x}', f'fmv.d.x f{other},x{scratch}']
        elif other != base and other != 0:
            lines.append(f'li x{other},{preload:#x}')
        lines += [f'li x{base},{address - case["offset"]:#x}', f'csrwi fflags,{case["fflags"]}',
            f'probe_{index}: .hword {encode(case):#x} # c.{case["name"]}']
        if fp:
            lines.append(f'fmv.x.d x{scratch},f{other}')
        value = expected(case) if load else a
        lines += [f'li x{check},{value:#x}', f'bne x{scratch if fp else other},x{check},fail']
        data = bytearray([0xa5] * 32)
        start = address - guard_address
        data[start:start + size] = (a & ((1 << (size * 8)) - 1)).to_bytes(size, 'little')
        for offset in range(0, 32, 8):
            value = int.from_bytes(data[offset:offset + 8], 'little')
            lines += [f'ld x{scratch},{offset}(x{guard})', f'li x{check},{value:#x}', f'bne x{scratch},x{check},fail']
        lines += [f'flags_{index}: csrr x{scratch},fflags', f'li x{check},{case["fflags"]}', f'bne x{scratch},x{check},fail']
    lines += ['li t1,1', 'j finish', '.balign 4', 'fail:li t1,3', 'finish:',
        'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt', '.section .tohost,"aw"',
        '.balign 8', '.globl tohost,fromhost', 'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, symbols, initial):
    targets = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    flags = {symbols[f'flags_{i}']: case for i, case in enumerate(plan, 1)}
    registers, fp, memory = [None] * 32, [None] * 32, initial.copy()
    registers[0] = 0
    counts, seen, flag_reads, writers, writes = {}, set(), set(), {}, {}
    misaligned, line_crossings, page_crossings, aliases = 0, 0, 0, 0
    def read(address, size):
        assert all(address + i in memory for i in range(size)), (hex(address), size)
        for i in range(size):
            if address + i in writers:
                writes[writers[address + i]]['observed'].add(address + i)
        return sum(memory[address + i] << (8 * i) for i in range(size))
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
        if pc in targets:
            case = targets[pc]
            load, floating, size, _ = attributes(case['name'])
            base, other, offset = case['base'], case['other'], case['offset']
            assert pc not in seen and word == encode(case)
            assert decode(word) == (case['name'], load, floating, size, base, other, offset)
            address = (registers[base] + offset) & MASK
            assert address == case['address']
            aliases += int(not floating and base == other)
            misaligned += address % size != 0
            line_crossings += address // 64 != (address + size - 1) // 64
            page_crossings += address // 4096 != (address + size - 1) // 4096
            if load:
                old = fp[other] if floating else registers[other]
                assert old == (expected(case) ^ MASK if floating or other != base else address - offset)
                value = read(address, size)
                value = (sx(value, 32) if not floating and size == 4 else value) & MASK
                assert value == expected(case)
                assert row['rd_write'] == '1' and int(row['rd_fp']) == floating and int(row['rd']) == other
                assert int(row['wdata'], 16) == value, (case, row)
            else:
                value = fp[other] if floating else registers[other]
                assert value == case['a'] and row['rd_write'] == '0'
                writes[index] = dict(addresses=set(range(address, address + size)), observed=set())
                write(address, size, value, index)
            assert int(rows[index + 1]['pc'], 16) == pc + 2
            counts[case['name']] = counts.get(case['name'], 0) + 1
            seen.add(pc)
        elif pc >= 0x80000000 and word & 127 in (3, 0x23):
            load, f3 = word & 127 == 3, (word >> 12) & 7
            base = registers[(word >> 15) & 31]
            assert base is not None
            imm = word >> 20 if load else (word >> 25) << 5 | (word >> 7) & 31
            address = (base + sx(imm, 12)) & MASK
            if load:
                _, size, signed = LOADS[f3]
                value = read(address, size)
                value = (sx(value, size * 8) if signed else value) & MASK
                rd = (word >> 7) & 31
                if rd:
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                    assert int(row['wdata'], 16) == value, row
            else:
                _, size = STORES[f3]
                value = registers[(word >> 20) & 31]
                assert value is not None
                write(address, size, value)
        if pc in flags:
            scratch = roles(flags[pc])[2]
            assert pc not in flag_reads and word == 1 << 20 | 2 << 12 | scratch << 7 | 0x73
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == scratch
            assert int(row['wdata'], 16) == flags[pc]['fflags']
            flag_reads.add(pc)
        if row['trap'] == '0' and row['rd_write'] == '1':
            rd, value = int(row['rd']), int(row['wdata'], 16)
            if row['rd_fp'] == '1':
                fp[rd] = value
            elif rd:
                registers[rd] = value
    assert len(seen) == len(flag_reads) == len(plan)
    assert all(item['observed'] == item['addresses'] for item in writes.values())
    return dict(probes=len(plan), forms=counts, checked_fflags_reads=len(flag_reads),
        fully_observed_stores=len(writes), integer_base_data_aliases=aliases,
        misaligned_accesses=misaligned, line_crossings=line_crossings, page_crossings=page_crossings)


def verifier(plan, folder):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        memory = initial_memory(folder / 'test.elf')
        result, controls = inspect(rows, plan, symbols, memory), []
        for name in result['forms']:
            case_index = next(i for i, case in enumerate(plan, 1) if case['name'] == name)
            index = next(i for i, row in enumerate(rows) if int(row['pc'], 16) == symbols[f'probe_{case_index}'])
            broken = copy.deepcopy(rows)
            if attributes(name)[0]:
                broken[index]['wdata'] = f"{int(broken[index]['wdata'], 16) ^ 1:016x}"
            else:
                addr, guard, scratch, check = roles(plan[case_index - 1])
                observer = next(row for row in broken[index + 1:] if int(row['instruction'], 16) & 0x7f == 3
                    and (int(row['instruction'], 16) >> 15) & 31 == guard)
                observer['wdata'] = f"{int(observer['wdata'], 16) ^ 1:016x}"
            try:
                inspect(broken, plan, symbols, memory)
            except AssertionError:
                controls.append(name)
            else:
                raise AssertionError(f'Incorrect C memory target/guard result accepted: {name}')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    plan = cases()
    FOLDER.mkdir(parents=True, exist_ok=True)
    batches = [plan[start:start + BATCH] for start in range(0, len(plan), BATCH)]
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='Finite native RV64C integer W/D and FP D memory field/byte sweep; all offset values with selected register/data combinations and deliberate misaligned/line/page crossings. Full operand Cartesian products, faults, permissions, MMIO atomicity and all schedules separate',
        inputs=source_inputs(DEPENDENCIES), probes=len(plan), cases=[])
    if args.check:
        saved = json.loads((FOLDER / 'report.json').read_bytes())
        assert saved['passed'] and saved['generator_sha256'] == top['generator_sha256']
        assert saved['inputs'] == top['inputs'] and saved['probes'] == len(plan) and len(saved['cases']) == len(batches)
    else:
        dump(FOLDER / 'report.json', top)
    for index, batch in enumerate(batches):
        folder = FOLDER / str(index)
        folder.mkdir(exist_ok=True)
        source, verify = folder / 'test.S', verifier(batch, folder)
        if args.check:
            outcome = check_fixture(folder, __file__, fixture(batch), verify)
            old = saved['cases'][index]
            assert old['index'] == index and old['report_sha256'] == sha(folder / 'report.json') and old['outcomes'] == outcome
        else:
            source.write_text(fixture(batch), encoding='utf-8')
            outcome = run_fixture(source, folder, __file__, verify,
                source_dependencies=DEPENDENCIES, timeout_cycles=2000000)
        top['cases'].append(dict(index=index, report_sha256=sha(folder / 'report.json'), outcomes=outcome))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS native RV64C memory', index, outcome['probes'], 'probes;',
            outcome['matched_events'], 'Sail/RTL events;', len(outcome['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

"""Native RV64 Zcb legal encodings, integer results and byte-memory oracle."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from audit_rv64i_compute_control import sx
from audit_rv64i_memory_values import initial_memory, inspect as byte_inspect
from audit_rv64m_contract import MASK
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/zcb_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/audit_rv64i_compute_control.py',
    'scripts/audit_rv64i_memory_values.py', 'scripts/audit_rv64m_contract.py']
UNARY = ['zext.b', 'sext.b', 'zext.h', 'sext.h', 'zext.w', 'not']
MEMORY = {'lbu': (True, 1, False, 0), 'lhu': (True, 2, False, 1),
          'lh': (True, 2, True, 1), 'sb': (False, 1, False, 2), 'sh': (False, 2, False, 3)}
VALUES = [0, MASK, 1, 0x80, 0xff, 0x8000, 0xffff, 0x80000000,
          0xffffffff, 0x0123456789abcdef, 1 << 63, 0xdeadbeef7fffffff]
DATA = [0, MASK, 0x80, 0xff, 0x8000, 0xffff, 0x80000000, 0x0123456789abcdef]
GUARD, FCSR, BATCH = 0xa5a5a5a5a5a5a5a5, 0x65, 256


def cases():
    plan = []
    for name in UNARY:
        for rd in range(8, 16):
            for a in VALUES:
                plan.append(dict(name=name, kind='alu', rd=rd, a=a, b=0, rs2=None))
    for rd in range(8, 16):
        for rs2 in range(8, 16):
            for index in range(len(VALUES)):
                a, b = VALUES[(rd - 8 + index) % len(VALUES)], VALUES[(rs2 - 8 + 3 * index + 5) % len(VALUES)]
                plan.append(dict(name='mul', kind='alu', rd=rd, rs2=rs2, a=a, b=a if rd == rs2 else b))
    def add_memory(name, base, other, offset, address, a):
        load, size, signed, code = MEMORY[name]
        if not load and other == base:
            a = address - offset
        plan.append(dict(name=name, kind='memory', base=base, rd=other,
            offset=offset, address=address, a=a))
    for name, (load, size, signed, code) in MEMORY.items():
        for base in range(8, 16):
            for other in range(8, 16):
                for offset in range(4) if size == 1 else (0, 2):
                    address = 0x80090000 + (((base - 8) * 8 + other * size) % 64)
                    add_memory(name, base, other, offset, address, DATA[(base + other + offset // size) % len(DATA)])
        for crossing in (1, 2, 7, 60, 63, 4095):
            for variant in range(2):
                add_memory(name, 9, 9, 1 + 2 * variant if size == 1 else 2,
                    0x80090000 + crossing, DATA[4 + variant])
    return plan


def encode(case):
    name, rd = case['name'], case['rd']
    if name == 'mul':
        return 0x9c41 | (rd - 8) << 7 | (case['rs2'] - 8) << 2
    if name in UNARY:
        return 0x9c61 | (rd - 8) << 7 | UNARY.index(name) << 2
    load, size, signed, code = MEMORY[name]
    offset = case['offset']
    return (0x8000 | code << 10 | (case['base'] - 8) << 7 | (rd - 8) << 2
        | ((offset >> 1) & 1) << 5 | ((offset & 1) if size == 1 else int(signed)) << 6)


def decode(word):
    if word & 3 == 0:
        assert word >> 13 == 4
        code = (word >> 10) & 7
        base, other = 8 + ((word >> 7) & 7), 8 + ((word >> 2) & 7)
        if code in (0, 2):
            name = 'lbu' if code == 0 else 'sb'
            offset = ((word >> 5) & 1) << 1 | ((word >> 6) & 1)
        else:
            assert code in (1, 3)
            assert code != 3 or word & 64 == 0
            name = ('lh' if word & 64 else 'lhu') if code == 1 else 'sh'
            offset = ((word >> 5) & 1) << 1
        return name, base, other, offset
    assert word & 3 == 1 and word >> 10 == 0x27
    rd, op = 8 + ((word >> 7) & 7), (word >> 5) & 3
    if op == 2:
        return 'mul', rd, 8 + ((word >> 2) & 7)
    assert op == 3 and ((word >> 2) & 7) < 6
    return UNARY[(word >> 2) & 7], rd, None


def expected(case):
    name, a = case['name'], case['a']
    if name in MEMORY:
        load, size, signed, code = MEMORY[name]
        raw = a & ((1 << (size * 8)) - 1)
        return (sx(raw, size * 8) if signed else raw) & MASK
    return {'zext.b': lambda: a & 255, 'sext.b': lambda: sx(a, 8),
        'zext.h': lambda: a & 65535, 'sext.h': lambda: sx(a, 16),
        'zext.w': lambda: a & 0xffffffff, 'not': lambda: a ^ MASK,
        'mul': lambda: a * case['b']}[name]() & MASK


def fixture(plan):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6000', 'csrs mstatus,t0', f'li t0,{FCSR}', 'csrw fcsr,t0']
    for index, case in enumerate(plan, 1):
        rd, a = case['rd'], case['a']
        if case['kind'] == 'alu':
            lines.append(f'li x{rd},{a:#x}')
            if case['rs2'] is not None and case['rs2'] != rd:
                lines.append(f'li x{case["rs2"]},{case["b"]:#x}')
        else:
            load, size, signed, code = MEMORY[case['name']]
            address, base = case['address'], case['base']
            lines += [f'li x16,{address:#x}', f'li x17,{(address & ~7) - 8:#x}', f'li x18,{GUARD:#x}']
            lines += [f'sd x18,{offset}(x17)' for offset in range(0, 32, 8)]
            if load:
                lines.append(f'li x18,{a:#x}')
                for offset in range(size):
                    lines += [f'sb x18,{offset}(x16)', 'srli x18,x18,8']
            if rd != base:
                lines.append(f'li x{rd},{(expected(case) ^ MASK) if load else a:#x}')
            lines.append(f'li x{base},{address - case["offset"]:#x}')
        lines += [f'probe_{index}:.hword {encode(case):#x} # c.{case["name"]}']
        value = a if case['kind'] == 'memory' and not MEMORY[case['name']][0] else expected(case)
        lines += [f'li x19,{value:#x}', f'bne x{rd},x19,fail']
        if case['name'] == 'mul' and case['rs2'] != rd:
            lines += [f'li x19,{case["b"]:#x}', f'bne x{case["rs2"]},x19,fail']
        if case['kind'] == 'memory':
            lines += [f'guard_{index}_{offset}:ld x18,{offset}(x17)' for offset in range(0, 32, 8)]
        lines += [f'state_{index}:csrr x18,fcsr', f'li x19,{FCSR}', 'bne x18,x19,fail']
    lines += ['li t1,1', 'j finish', '.balign 4', 'fail:li t1,3', 'finish:',
        'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt', '.section .tohost,"aw"',
        '.balign 8', '.globl tohost,fromhost', 'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, symbols, memory):
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    states = {symbols[f'state_{i}'] for i in range(1, len(plan) + 1)}
    guards = {symbols[f'guard_{i}_{offset}']: (i, case, offset)
        for i, case in enumerate(plan, 1) if case['kind'] == 'memory' for offset in range(0, 32, 8)}
    registers, seen, state_reads, guard_reads, forms, canonical = [None] * 32, set(), set(), set(), {}, []
    registers[0] = 0
    writes, observed, misaligned, line_crossings, page_crossings, aliases = {}, {}, 0, 0, 0, 0
    for row_index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        assert pc < 0x80000000 or row['trap'] == '0', row
        converted = row.copy()
        if pc in probes:
            case = probes[pc]
            rd = case['rd']
            assert pc not in seen and word == encode(case)
            if case['kind'] == 'alu':
                assert decode(word) == (case['name'], rd, case['rs2'])
                assert registers[rd] == case['a']
                if case['rs2'] is not None:
                    assert registers[case['rs2']] == case['b']
                load = True
            else:
                base, offset, address = case['base'], case['offset'], case['address']
                assert decode(word) == (case['name'], base, rd, offset)
                assert (registers[base] + offset) & MASK == address
                load, size, signed, code = MEMORY[case['name']]
                misaligned += address % size != 0
                line_crossings += address // 64 != (address + size - 1) // 64
                page_crossings += address // 4096 != (address + size - 1) // 4096
                aliases += base == rd
                f3 = (4 if size == 1 else 1 if signed else 5) if load else (0 if size == 1 else 1)
                expanded = (offset << 20 | base << 15 | f3 << 12 | rd << 7 | 3) if load else (
                    (offset >> 5) << 25 | rd << 20 | base << 15 | f3 << 12 | (offset & 31) << 7 | 0x23)
                # Semantic expansion only for the independent byte oracle;
                # Sail comparison and all raw/length checks retain the 16-bit instruction.
                converted['instruction'] = f'{expanded:08x}'
                if not load:
                    assert registers[rd] == case['a']
                    writes[pc] = set(range(address, address + size))
                    observed[pc] = set()
            if load:
                assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                assert int(row['wdata'], 16) == expected(case), (case, row)
            else:
                assert row['rd_write'] == '0'
            assert int(rows[row_index + 1]['pc'], 16) == pc + 2
            seen.add(pc)
            forms[case['name']] = forms.get(case['name'], 0) + 1
        if pc in guards:
            index, case, offset = guards[pc]
            assert pc not in guard_reads and word == offset << 20 | 17 << 15 | 3 << 12 | 18 << 7 | 3
            address = (case['address'] & ~7) - 8
            assert registers[17] == address
            owner = symbols[f'probe_{index}']
            if owner in observed:
                observed[owner].update(writes[owner] & set(range(address + offset, address + offset + 8)))
            guard_reads.add(pc)
        if pc in states:
            assert pc not in state_reads and word == 0x00302973
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '18'
            assert int(row['wdata'], 16) == FCSR
            state_reads.add(pc)
        canonical.append(converted)
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    assert len(seen) == len(state_reads) == len(plan) and guard_reads == set(guards)
    assert all(observed[pc] == addresses for pc, addresses in writes.items())
    coverage = byte_inspect(canonical, memory)
    return dict(probes=len(plan), forms=forms, fully_observed_target_stores=len(writes),
        misaligned_accesses=misaligned, line_crossings=line_crossings, page_crossings=page_crossings,
        memory_base_data_aliases=aliases, checked_fcsr_reads=len(state_reads), byte_oracle_coverage=coverage)


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
            index = next(i for i, case in enumerate(plan, 1) if case['name'] == name)
            case = plan[index - 1]
            broken = copy.deepcopy(rows)
            if name in MEMORY and not MEMORY[name][0]:
                pc, bit = symbols[f'guard_{index}_8'], 1 << ((case['address'] & 7) * 8)
            else:
                pc, bit = symbols[f'probe_{index}'], 1
            row = next(row for row in broken if int(row['pc'], 16) == pc)
            row['wdata'] = f"{int(row['wdata'], 16) ^ bit:016x}"
            try:
                inspect(broken, plan, symbols, memory)
            except AssertionError:
                controls.append(name)
            else:
                raise AssertionError(f'Incorrect Zcb result/observed byte accepted: {name}')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    plan = cases()
    assert len({encode(case) for case in plan}) == 1008
    FOLDER.mkdir(parents=True, exist_ok=True)
    batches = [plan[start:start + BATCH] for start in range(0, len(plan), BATCH)]
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='All 1008 legal RV64 Zcb encodings executed with selected data, narrow-memory aliases/misalignment/line/page crossings and independent integer/byte oracles. M-mode only; optional feature-disabled legality, every operand, faults/permissions, timing and all schedules separate',
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
                source_dependencies=DEPENDENCIES, timeout_cycles=3000000)
        top['cases'].append(dict(index=index, report_sha256=sha(folder / 'report.json'), outcomes=outcome))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS native Zcb', index, outcome['probes'], 'probes;', outcome['matched_events'],
            'Sail/RTL events;', len(outcome['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

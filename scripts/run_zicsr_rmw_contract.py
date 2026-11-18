"""Native six-form CSR RMW, encoded-zero write intent and deterministic instret."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from audit_rv64m_contract import MASK
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump


FOLDER = ROOT / 'out/rva23/zicsr_rmw_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/audit_rv64m_contract.py']
CSRS = {'mscratch': 0x340, 'minstret': 0xb02, 'mhartid': 0xf14}
SENTINEL = 0x55aa123489abcdef


def cases():
    plan = []
    for name, csr in CSRS.items():
        for f3 in (1, 2, 3, 5, 6, 7):
            for rd in (0, 5, 31):
                operands = [(reg, value) for reg in (0, 5, 31)
                    for value in ((0,) if reg == 0 else (0, 1, MASK, 1 << 63))] if f3 < 4 else [
                    (imm, imm) for imm in (0, 1, 15, 16, 31)]
                for source, value in operands:
                    write = f3 & 3 == 1 or source != 0
                    plan.append(dict(name=name, csr=csr, f3=f3, rd=rd, source=source,
                        value=value, word=csr << 20 | source << 15 | f3 << 12 | rd << 7 | 0x73,
                        cause=2 if name == 'mhartid' and write else 0))
    return plan


def fixture():
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,trap_handler', 'csrw mtvec,t0', 'csrw mcountinhibit,zero', 'csrw minstret,zero',
        'li t0,0x1234', 'counter_write_adjacent:csrw minstret,t0',
        'counter_next_read:csrr t1,minstret', 'counter_second_read:csrr t2,minstret',
        'li s1,0x1234', 'bne t1,s1,fail', 'addi s1,s1,1', 'bne t2,s1,fail']
    for index, case in enumerate(cases(), 1):
        lines += [f'la x16,probe_{index}', f'la x17,after_{index}',
            f'li x18,{case["cause"]}', f'li x19,{case["word"]:#x}', 'li x20,0']
        if case['name'] != 'mhartid':
            initial = 0x1234567887654321 if case['name'] == 'mscratch' else 0x200
            lines += [f'li t2,{initial:#x}', f'csrw {case["name"]},t2']
        if case['rd'] and not (case['f3'] < 4 and case['rd'] == case['source']):
            lines.append(f'li x{case["rd"]},{SENTINEL:#x}')
        if case['f3'] < 4 and case['source']:
            lines.append(f'li x{case["source"]},{case["value"]:#x}')
        lines += [f'probe_{index}:.word {case["word"]:#x}', f'after_{index}:li t1,{int(bool(case["cause"]))}',
            'bne x20,t1,fail', f'readback_{index}:csrr t1,{case["name"]}']
    lines += ['li t1,1', 'j finish', '.balign 4', 'trap_handler:',
        'csrr t1,mcause', 'bne t1,x18,fail', 'csrr t1,mtval', 'bne t1,x19,fail',
        'csrr t1,mepc', 'bne t1,x16,fail', 'addi x20,x20,1', 'csrw mepc,x17', 'mret',
        'fail:li t1,3', 'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, symbols):
    plan = cases()
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    readbacks = {symbols[f'readback_{i}']: case for i, case in enumerate(plan, 1)}
    registers, csrs = [None] * 32, {0x340: None, 0xb02: None, 0xf14: 0}
    registers[0] = 0
    seen, reads, traps, forms = set(), set(), [], {}
    zero_data_writes, alias_sources, instret_reads, explicit_counter_writes = 0, 0, 0, 0
    adjacent_values = []
    assert symbols['counter_next_read'] == symbols['counter_write_adjacent'] + 4
    assert symbols['counter_second_read'] == symbols['counter_next_read'] + 4
    for row_index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if pc < 0x80000000:
            if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
                registers[int(row['rd'])] = int(row['wdata'], 16)
            continue
        trap = row['trap'] == '1'
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and word == case['word'] and trap == bool(case['cause'])
            if case['f3'] < 4:
                assert registers[case['source']] == case['value']
                zero_data_writes += int(case['f3'] in (2, 3) and case['source'] != 0 and case['value'] == 0)
                alias_sources += int(case['rd'] == case['source'] and case['rd'] != 0)
            if trap:
                assert int(row['cause']) == case['cause'] and int(row['tval'], 16) == word
                assert row['rd_write'] == '0'
                assert int(rows[row_index + 1]['pc'], 16) == symbols['trap_handler']
                traps.append((pc, case['cause']))
            else:
                assert int(rows[row_index + 1]['pc'], 16) == pc + 4
            forms[case['f3']] = forms.get(case['f3'], 0) + 1
            seen.add(pc)
        elif trap:
            raise AssertionError(('Unexpected trap', row))
        counter_written = False
        csr = word >> 20
        f3, source, rd = (word >> 12) & 7, (word >> 15) & 31, (word >> 7) & 31
        if word & 127 == 0x73 and f3 in (1, 2, 3, 5, 6, 7) and csr in csrs:
            cmd = f3 & 3
            operand = source if f3 >= 5 else registers[source]
            assert operand is not None
            write = cmd == 1 or source != 0
            old = csrs[csr]
            illegal = csr == 0xf14 and write
            assert trap == illegal, row
            if not illegal:
                if rd:
                    assert old is not None
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                    assert int(row['wdata'], 16) == old, (hex(csr), row, old)
                    instret_reads += int(csr == 0xb02)
                if write:
                    value = operand if cmd == 1 else (old | operand if cmd == 2 else old & ~operand)
                    csrs[csr] = value & MASK
                    counter_written = csr == 0xb02
                    explicit_counter_writes += int(counter_written)
        if pc in readbacks:
            assert pc not in reads and row['trap'] == '0'
            assert word == readbacks[pc]['csr'] << 20 | 2 << 12 | 6 << 7 | 0x73
            reads.add(pc)
        if pc in (symbols['counter_next_read'], symbols['counter_second_read']):
            adjacent_values.append(int(row['wdata'], 16))
        if not trap and not counter_written and csrs[0xb02] is not None:
            csrs[0xb02] = (csrs[0xb02] + 1) & MASK
        if not trap and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    assert len(seen) == len(reads) == len(plan)
    expected = [(symbols[f'probe_{i}'], case['cause']) for i, case in enumerate(plan, 1) if case['cause']]
    assert traps == expected
    assert adjacent_values == [0x1234, 0x1235]
    return dict(probes=len(plan), forms={str(key): value for key, value in forms.items()},
        exact_readonly_traps=len(traps), encoded_nonzero_zero_data_rmw=zero_data_writes,
        rd_rs1_aliases=alias_sources, checked_instret_reads=instret_reads,
        explicit_counter_writes=explicit_counter_writes, adjacent_counter_values=adjacent_values)


def verify(sail_trace, rtl_trace):
    rows = read_csv(rtl_trace)
    nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(FOLDER / 'test.elf')], text=True)
    symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
    result = inspect(rows, symbols)
    events, mismatch = compare(read_csv(sail_trace), rows)
    assert mismatch is None, mismatch
    controls = []
    selectors = {
        'csr_old_value': lambda row: int(row['pc'], 16) == symbols['probe_2'],
        'readback': lambda row: int(row['pc'], 16) == symbols['readback_1'],
        'counter_read': lambda row: int(row['pc'], 16) >= 0x80000000 and int(row['instruction'], 16) == 0xb0202373,
        'readonly_cause': lambda row: int(row['pc'], 16) >= 0x80000000 and row['trap'] == '1',
        'readonly_tval': lambda row: int(row['pc'], 16) >= 0x80000000 and row['trap'] == '1'}
    # Select a nonzero destination CSR probe without depending on case ordering.
    target = next(symbols[f'probe_{i}'] for i, case in enumerate(cases(), 1) if case['rd'] and not case['cause'])
    selectors['csr_old_value'] = lambda row: int(row['pc'], 16) == target
    for name, select in selectors.items():
        broken = copy.deepcopy(rows)
        row = next(row for row in broken if select(row))
        key = 'cause' if name == 'readonly_cause' else 'tval' if name == 'readonly_tval' else 'wdata'
        value = int(row[key], 10 if key == 'cause' else 16) ^ 1
        row[key] = str(value) if key == 'cause' else f'{value:016x}'
        try:
            inspect(broken, symbols)
        except AssertionError:
            controls.append(name)
        else:
            raise AssertionError(f'Incorrect {name} accepted')
    return dict(**result, matched_events=events, rejected_mutations=controls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    if args.check:
        result = check_fixture(FOLDER, __file__, fixture(), verify)
    else:
        source = FOLDER / 'test.S'
        source.write_text(fixture(), encoding='utf-8')
        result = run_fixture(source, FOLDER, __file__, verify,
            source_dependencies=DEPENDENCIES, timeout_cycles=3000000)
    print('PASS six-form Zicsr RMW:', result['probes'], 'probes;', result['matched_events'],
        'Sail/RTL events;', result['exact_readonly_traps'], 'readonly traps;',
        len(result['rejected_mutations']), 'rejected mutations', flush=True)


if __name__ == '__main__':
    main()

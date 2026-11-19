"""Native M rd=x0 edges and reserved OP-32 funct3 precise traps."""
import argparse
import copy
import subprocess

from audit_hv_sail_fixture import check_fixture
from audit_rv64m_contract import MASK, OPS
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT

FOLDER = ROOT / 'out/rva23/rv64m_encoding_edges'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/audit_rv64m_contract.py']
PAIRS = [(0, 0), (1 << 63, MASK), (0x80000000, MASK), (MASK, 0), (0xfedcba9876543210, 7)]


def cases():
    plan = []
    for (opcode, f3), name in OPS.items():
        for a, b in PAIRS:
            plan.append(dict(name=name, word=1 << 25 | 9 << 20 | 8 << 15 | f3 << 12 | opcode,
                a=a, b=b, cause=0))
    for f3 in (1, 2, 3):
        for rd in (0, 1, 31):
            for rs1, rs2 in ((8, 9), (0, 0), (31, 1), (1, 31)):
                plan.append(dict(name='reserved', word=1 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | rd << 7 | 0x3b,
                    a=MASK, b=0, cause=2))
    assert len(plan) == 101
    return plan


def observations(plan):
    return {f'value_{i}_{name}': (word, value) for i, case in enumerate(plan, 1)
        for name, word, value in [('a', 8 << 15 | 7 << 7 | 0x13, case['a']),
            ('b', 9 << 15 | 7 << 7 | 0x13, case['b']), ('ra', 1 << 15 | 7 << 7 | 0x13, 0x1234),
            ('last', 31 << 15 | 7 << 7 | 0x13, 0x5678), ('fcsr', 0x003023f3, 0x65)]}


def fixture(plan):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,m_trap', 'csrw mtvec,t0', 'li t0,0x6000', 'csrw mstatus,t0', 'li t0,0x65', 'csrw fcsr,t0']
    values = observations(plan)
    for i, case in enumerate(plan, 1):
        lines += [f'li s4,{i}', f'li s5,{case["word"]:#x}', f'la s6,probe_{i}', 'li s7,0',
            f'li x8,{case["a"]:#x}', f'li x9,{case["b"]:#x}', 'li ra,0x1234', 'li t6,0x5678',
            f'probe_{i}:.word {case["word"]:#x}', f'li t0,{int(bool(case["cause"]))}', 'bne s7,t0,fail']
        for name, instruction in [('a', 'mv t2,s0'), ('b', 'mv t2,s1'), ('ra', 'mv t2,ra'),
                ('last', 'mv t2,t6'), ('fcsr', 'csrr t2,fcsr')]:
            label = f'value_{i}_{name}'
            lines += [f'{label}:{instruction}', f'li t3,{values[label][1]:#x}', 'bne t2,t3,fail']
    lines += ['li t1,1', 'j finish', 'm_trap:', 'csrr t0,mcause', 'li t1,2', 'bne t0,t1,fail',
        'bnez s7,fail', 'csrr t0,mepc', 'bne t0,s6,fail', 'csrr t1,mtval', 'bne t1,s5,fail',
        'li s7,1', 'addi t0,t0,4', 'csrw mepc,t0', 'mret', 'fail:li t1,3',
        'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt', '.section .tohost,"aw"',
        '.balign 8', '.globl tohost,fromhost', 'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, symbols):
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    reads = {symbols[name]: value for name, value in observations(plan).items()}
    seen, observed, traps = set(), set(), []
    for index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if pc >= 0x80000000 and row['trap'] == '1':
            traps.append(pc)
            assert pc in probes
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and word == case['word'] and row['rd_write'] == '0'
            assert (row['trap'] == '1') == bool(case['cause'])
            if case['cause']:
                assert int(row['cause']) == 2 and int(row['tval'], 16) == word
                assert int(rows[index + 1]['pc'], 16) == symbols['m_trap']
            else:
                assert int(rows[index + 1]['pc'], 16) == pc + 4
            seen.add(pc)
        if pc in reads:
            instruction, value = reads[pc]
            assert pc not in observed and word == instruction and row['trap'] == '0'
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '7'
            assert int(row['wdata'], 16) == value, row
            observed.add(pc)
    assert seen == set(probes) and observed == set(reads)
    assert traps == [symbols[f'probe_{i}'] for i, case in enumerate(plan, 1) if case['cause']]
    return dict(legal_zero_destination=sum(not case['cause'] for case in plan),
        reserved_traps=len(traps), preserved_values=len(observed), forms=sorted({case['name'] for case in plan if not case['cause']}))


def verifier(plan):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(FOLDER / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        result, controls = inspect(rows, plan, symbols), []
        for kind in ('reserved_cause', 'reserved_tval', 'zero_destination_write', 'preserved_source'):
            broken = copy.deepcopy(rows)
            if kind.startswith('reserved'):
                pc = symbols[f'probe_{next(i for i, case in enumerate(plan, 1) if case["cause"])}']
            else:
                pc = symbols['probe_1' if kind == 'zero_destination_write' else 'value_1_a']
            row = next(row for row in broken if int(row['pc'], 16) == pc)
            if kind == 'reserved_cause': row['cause'] = '22'
            elif kind == 'reserved_tval': row['tval'] = f'{int(row["tval"], 16) ^ 1:016x}'
            elif kind == 'zero_destination_write': row['rd_write'] = '1'
            else: row['wdata'] = f'{int(row["wdata"], 16) ^ 1:016x}'
            try:
                inspect(broken, plan, symbols)
            except AssertionError:
                controls.append(kind)
            else:
                raise AssertionError('Incorrect M encoding edge accepted')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    plan = cases()
    FOLDER.mkdir(parents=True, exist_ok=True)
    source, verify = FOLDER / 'test.S', verifier(plan)
    if args.check:
        result = check_fixture(FOLDER, __file__, fixture(plan), verify)
    else:
        source.write_text(fixture(plan), encoding='utf-8')
        result = run_fixture(source, FOLDER, __file__, verify, source_dependencies=DEPENDENCIES, timeout_cycles=1000000)
    print('PASS RV64M encoding edges', result, flush=True)


if __name__ == '__main__':
    main()

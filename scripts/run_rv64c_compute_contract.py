"""Sweep RV64 compressed integer compute fields on native H/V RTL and Sail."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from audit_rv64c_contract import decode
from audit_rv64i_compute_control import sx
from audit_rv64m_contract import MASK
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/rv64c_compute_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/audit_rv64c_contract.py',
    'scripts/audit_rv64i_compute_control.py', 'scripts/audit_rv64i_memory_values.py',
    'scripts/audit_rv64m_contract.py']
VALUES = [0, MASK, 1, 0x8000000000000000, 0x7fffffff, 0x80000000,
          0xdeadbeef7fffffff, 0x0123456789abcdef]
REQUIRED = set('addi addiw li lui srli srai slli andi addi16sp addi4spn sub xor or and subw addw mv add'.split())
BATCH = 600


def expected(case):
    name, a, b, imm = (case[key] for key in ('name', 'a', 'b', 'imm'))
    if name in ('addi', 'addi16sp', 'addi4spn', 'addiw'):
        value = a + imm
    elif name == 'li':
        value = imm
    elif name == 'lui':
        value = imm << 12
    elif name == 'andi':
        value = a & imm
    elif name == 'slli':
        value = a << imm
    elif name == 'srli':
        value = a >> imm
    elif name == 'srai':
        value = sx(a, 64) >> imm
    else:
        value = {'sub': lambda: a - b, 'xor': lambda: a ^ b,
            'or': lambda: a | b, 'and': lambda: a & b,
            'subw': lambda: a - b, 'addw': lambda: a + b,
            'mv': lambda: b, 'add': lambda: a + b}[name]()
    return (sx(value, 32) if name in ('addiw', 'subw', 'addw') else value) & MASK


def cases():
    plan = []
    def add(name, word, rd, a=0, b=0, imm=0, rs2=None):
        if rs2 == rd:
            b = a
        case = dict(name=name, word=word, rd=rd, a=a, b=b, imm=imm)
        value = expected(case)
        inputs = {rd: a}
        if name in ('li', 'lui'):
            inputs = {rd: value ^ MASK}
        elif name == 'addi4spn':
            inputs = {2: a, rd: value ^ MASK}
        if rs2 is not None:
            inputs[rs2] = b
        case['inputs'] = inputs
        plan.append(case)
    def ci(base, rd, imm):
        return base | rd << 7 | ((imm & 63) >> 5) << 12 | (imm & 31) << 2
    for name, base in [('addi', 1), ('addiw', 0x2001), ('andi', 0x8801)]:
        for imm in range(-32, 32):
            for index, a in enumerate(VALUES):
                rd = 8 + (index + imm) % 8 if name == 'andi' else 1 + (index + imm) % 31
                word = ci(base, rd - 8 if name == 'andi' else rd, imm)
                add(name, word, rd, a=a, imm=imm)
    for name, base in [('li', 0x4001), ('lui', 0x6001)]:
        for imm in range(-32, 32):
            if name == 'lui' and not imm:
                continue
            for rd in (1, 8, 31):
                add(name, ci(base, rd, imm), rd, imm=imm)
    for name, base in [('slli', 2), ('srli', 0x8001), ('srai', 0x8401)]:
        for shift in range(64):
            for index, a in enumerate(VALUES):
                rd = 1 + (index + shift) % 31 if name == 'slli' else 8 + (index + shift) % 8
                word = ci(base, rd if name == 'slli' else rd - 8, shift)
                add(name, word, rd, a=a, imm=shift)
    for imm in range(-512, 512, 16):
        if not imm:
            continue
        word = (0x6101 | ((imm >> 9) & 1) << 12 | ((imm >> 7) & 3) << 3
                | ((imm >> 6) & 1) << 5 | ((imm >> 5) & 1) << 2 | ((imm >> 4) & 1) << 6)
        for a in (0, MASK, 0x0123456789abcdef):
            add('addi16sp', word, 2, a=a, imm=imm)
    for imm in range(4, 1024, 4):
        for index, a in enumerate((MASK, 0x0123456789abcdef)):
            rd = 8 + ((imm // 4 + index) % 8)
            word = ((rd - 8) << 2 | ((imm >> 6) & 15) << 7 | ((imm >> 4) & 3) << 11
                    | ((imm >> 3) & 1) << 5 | ((imm >> 2) & 1) << 6)
            add('addi4spn', word, rd, a=a, imm=imm)
    for name, base in [('sub', 0x8c01), ('xor', 0x8c21), ('or', 0x8c41),
                       ('and', 0x8c61), ('subw', 0x9c01), ('addw', 0x9c21)]:
        for rd in range(8, 16):
            for rs2 in range(8, 16):
                for index in range(3):
                    a, b = VALUES[(rd + index) % 8], VALUES[(rs2 + index + 2) % 8]
                    add(name, base | (rd - 8) << 7 | (rs2 - 8) << 2,
                        rd, a=a, b=b, rs2=rs2)
    for name, base in [('mv', 0x8002), ('add', 0x9002)]:
        for rd in range(1, 32):
            for rs2 in range(1, 32):
                add(name, base | rd << 7 | rs2 << 2, rd,
                    a=VALUES[rd % 8], b=VALUES[rs2 % 8], rs2=rs2)
    return plan


def fixture(plan):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0']
    for index, case in enumerate(plan, 1):
        scratch = next(reg for reg in (5, 6, 7) if reg not in case['inputs'])
        lines += [f'li x{reg},{value:#x}' for reg, value in case['inputs'].items()]
        lines += [f'probe_{index}: .hword {case["word"]:#x} # c.{case["name"]}',
            f'li x{scratch},{expected(case):#x}', f'bne x{case["rd"]},x{scratch},fail']
    lines += ['li t1,1', 'j finish', 'fail: li t1,3', 'finish:',
        'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt', '.section .tohost,"aw"',
        '.balign 8', '.globl tohost,fromhost', 'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, symbols):
    targets = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    registers, seen, counts = [None] * 32, set(), {}
    registers[0] = 0
    for index, row in enumerate(rows):
        pc = int(row['pc'], 16)
        if pc >= 0x80000000:
            assert row['trap'] == '0', row
        if pc in targets:
            case = targets[pc]
            assert pc not in seen and int(row['instruction'], 16) == case['word']
            for reg, value in case['inputs'].items():
                assert registers[reg] == value, (case, reg, registers[reg])
            item = decode(case['word'], pc, registers)
            assert item[:3] == (case['name'], case['rd'], expected(case)), (case, item)
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == case['rd']
            assert int(row['wdata'], 16) == expected(case), (case, row)
            assert int(rows[index + 1]['pc'], 16) == pc + 2
            counts[case['name']] = counts.get(case['name'], 0) + 1
            seen.add(pc)
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    assert len(seen) == len(plan)
    return dict(probes=len(plan), forms=counts)


def verifier(plan, folder):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        result, controls = inspect(rows, plan, symbols), []
        for name in result['forms']:
            case_index = next(i for i, case in enumerate(plan, 1) if case['name'] == name)
            pc = symbols[f'probe_{case_index}']
            index = next(i for i, row in enumerate(rows) if int(row['pc'], 16) == pc)
            for kind in ('result', 'next_pc'):
                broken = copy.deepcopy(rows)
                row, key = (broken[index], 'wdata') if kind == 'result' else (broken[index + 1], 'pc')
                row[key] = f"{int(row[key], 16) ^ (1 if kind == 'result' else 2):016x}"
                try:
                    inspect(broken, plan, symbols)
                except AssertionError:
                    controls.append(dict(name=name, kind=kind))
                else:
                    raise AssertionError(f'Incorrect C.{name} {kind} accepted')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    plan = cases()
    assert {case['name'] for case in plan} == REQUIRED
    FOLDER.mkdir(parents=True, exist_ok=True)
    batches = [plan[start:start + BATCH] for start in range(0, len(plan), BATCH)]
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='Finite native RV64C compute field sweep; full immediate/shift domains combined with selected data, all MV/ADD register pairs; memory, control, reserved encodings, permissions and all pipeline schedules separate',
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
        print('PASS native RV64C compute', index, outcome['probes'], 'probes;',
            outcome['matched_events'], 'Sail/RTL events;', len(outcome['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

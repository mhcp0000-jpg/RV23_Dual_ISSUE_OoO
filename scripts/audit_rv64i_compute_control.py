"""Audit finite RV64I compute/control traces with independent integer/PC rules."""
import copy
import json

from audit_rv64m_contract import MASK, signed
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, dump, sha, source_inputs


REQUIRED = set('''add sub sll slt sltu xor srl sra or and
    addi slti sltiu xori ori andi slli srli srai
    addw subw sllw srlw sraw addiw slliw srliw sraiw
    lui auipc beq bne blt bge bltu bgeu jal jalr'''.split())


def sx(value, width):
    return signed(value & ((1 << width) - 1), width)


def decode(word, pc, registers):
    opcode, funct3, funct7 = word & 0x7f, (word >> 12) & 7, word >> 25
    rd, rs1, rs2 = (word >> 7) & 31, (word >> 15) & 31, (word >> 20) & 31
    immediate = sx(word >> 20, 12)

    def reg(index):
        assert registers[index] is not None, (hex(pc), hex(word), index)
        return registers[index]

    if opcode in (0x37, 0x17):
        result = sx(word & 0xfffff000, 32)
        return ('lui' if opcode == 0x37 else 'auipc',
                (result + (pc if opcode == 0x17 else 0)) & MASK, (pc + 4) & MASK, None)
    if opcode in (0x6f, 0x67, 0x63):
        if opcode == 0x6f:
            offset = ((word >> 31) << 20 | ((word >> 12) & 255) << 12
                      | ((word >> 20) & 1) << 11 | ((word >> 21) & 1023) << 1)
            return 'jal', (pc + 4) & MASK, (pc + sx(offset, 21)) & MASK, None
        if opcode == 0x67 and funct3 == 0:
            return 'jalr', (pc + 4) & MASK, ((reg(rs1) + immediate) & MASK) & ~1, None
        if opcode == 0x63 and funct3 in (0, 1, 4, 5, 6, 7):
            a, b = reg(rs1), reg(rs2)
            name, taken = {0: ('beq', a == b), 1: ('bne', a != b),
                4: ('blt', sx(a, 64) < sx(b, 64)), 5: ('bge', sx(a, 64) >= sx(b, 64)),
                6: ('bltu', a < b), 7: ('bgeu', a >= b)}[funct3]
            offset = ((word >> 31) << 12 | ((word >> 7) & 1) << 11
                      | ((word >> 25) & 63) << 5 | ((word >> 8) & 15) << 1)
            return name, None, (pc + sx(offset, 13) if taken else pc + 4) & MASK, taken
        return None
    if opcode not in (0x13, 0x1b, 0x33, 0x3b):
        return None
    word_form = opcode in (0x1b, 0x3b)
    immediate_form = opcode in (0x13, 0x1b)
    if not immediate_form and funct7 not in (0, 32):
        return None
    names = {0: 'add', 1: 'sll', 2: 'slt', 3: 'sltu', 4: 'xor', 5: 'srl', 6: 'or', 7: 'and'}
    if word_form and funct3 not in (0, 1, 5):
        return None
    name = names[funct3]
    if funct3 in (1, 5):
        upper = word >> (25 if word_form else 26)
        legal_upper = (0, 32 if word_form else 16) if funct3 == 5 else (0,)
        if immediate_form and upper not in legal_upper:
            return None
    if funct3 == 5 and word & (1 << 30):
        name = 'sra'
    if not immediate_form and funct7 == 32:
        if funct3 == 0:
            name = 'sub'
        elif funct3 != 5:
            return None
    a = reg(rs1)
    b = immediate & MASK if immediate_form else reg(rs2)
    width = 32 if word_form else 64
    shift = (word >> 20 if immediate_form else b) & (width - 1)
    left = a & ((1 << width) - 1)
    result = {'add': lambda: a + b, 'sub': lambda: a - b,
        'sll': lambda: left << shift, 'srl': lambda: left >> shift,
        'sra': lambda: sx(left, width) >> shift,
        'slt': lambda: int(sx(a, 64) < sx(b, 64)), 'sltu': lambda: int(a < b),
        'xor': lambda: a ^ b, 'or': lambda: a | b, 'and': lambda: a & b}[name]()
    if immediate_form:
        name = 'sltiu' if name == 'sltu' else name + 'i'
    if word_form:
        name += 'w'
        result = sx(result, 32)
    return name, result & MASK, (pc + 4) & MASK, None


def inspect(rows):
    registers, counts = [None] * 32, {}
    registers[0] = 0
    for index, row in enumerate(rows):
        word, pc = int(row['instruction'], 16), int(row['pc'], 16)
        if pc >= 0x80000000 and row['trap'] == '0':
            decoded = decode(word, pc, registers)
            if decoded:
                name, result, next_pc, taken = decoded
                rd = (word >> 7) & 31
                if result is not None and rd:
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                    assert int(row['wdata'], 16) == result, (name, row, hex(result))
                if index + 1 < len(rows):
                    assert int(rows[index + 1]['pc'], 16) == next_pc, (name, row, hex(next_pc))
                stats = counts.setdefault(name, dict(operations=0, zero_destination=0,
                    taken=0, not_taken=0))
                stats['operations'] += 1
                stats['zero_destination'] += result is not None and rd == 0
                if taken is not None:
                    stats['taken'] += taken
                    stats['not_taken'] += not taken
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    return counts


def main():
    report = ROOT / 'out/rva23/sail_upstream_comparison/report.json'
    base = json.loads(report.read_bytes())
    assert base['passed'] and source_inputs(base['inputs']) == base['inputs']
    model, reference = base['model'], base['reference']
    assert source_inputs(model['inputs']) == model['inputs']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    assert sha(ROOT / reference['binary']) == reference['binary_sha256']
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(model['params'])
    cases = [case for case in base['cases'] if case['name'] in {'rv64ui/' + name for name in REQUIRED}]
    assert len(cases) == len(REQUIRED) == 38
    artifacts, outcomes, controls = {}, {}, []
    for case in cases:
        assert case['reference_passed'] and case['rtl_passed']
        assert case['rtl_model_sha256'] == model['binary_sha256']
        assert case['reference_binary_sha256'] == reference['binary_sha256']
        for key in ('elf', 'rtl_trace', 'sail_trace', 'sail_log'):
            assert sha(ROOT / case[key]) == case[key + '_sha256']
            artifacts[case[key]] = case[key + '_sha256']
        run = case['rtl']
        assert run['passed'] and run['exit_code'] == 0 and sha(ROOT / run['log']) == run['log_sha256']
        artifacts[run['log']] = run['log_sha256']
        actual, sail = read_csv(ROOT / case['rtl_trace']), read_csv(ROOT / case['sail_trace'])
        events, mismatch = compare(sail, actual)
        assert mismatch is None, mismatch
        coverage = inspect(actual)
        name = case['name'].split('/')[1]
        assert coverage[name]['operations'] > 0
        if name.startswith('b'):
            assert coverage[name]['taken'] > 0 and coverage[name]['not_taken'] > 0
        outcomes[name] = dict(matched_events=events, coverage=coverage)
        registers = [None] * 32
        registers[0] = 0
        broken = copy.deepcopy(actual)
        for index, row in enumerate(actual):
            word, pc = int(row['instruction'], 16), int(row['pc'], 16)
            item = decode(word, pc, registers) if pc >= 0x80000000 and row['trap'] == '0' else None
            if item and item[0] == name and index + 1 < len(actual):
                if name in ('jal', 'jalr') or name.startswith('b'):
                    broken[index + 1]['pc'] = f"{int(broken[index + 1]['pc'], 16) ^ 2:016x}"
                    break
                if item[1] is not None and (word >> 7) & 31:
                    broken[index]['wdata'] = f"{int(row['wdata'], 16) ^ 1:016x}"
                    break
            if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
                registers[int(row['rd'])] = int(row['wdata'], 16)
        else:
            raise AssertionError(f'No mutation candidate for {name}')
        try:
            inspect(broken)
        except AssertionError:
            controls.append(name)
        else:
            raise AssertionError(f'Incorrect {name} result/target accepted')
    dump(ROOT / 'out/rva23/rv64i_compute_control_audit.json', dict(
        passed=True, complete_profile_validation=False,
        scope='Finite RV64I compute/control retirement evidence; memory, traps, FENCE and exhaustive pipeline schedules remain separate',
        base_report_sha256=sha(report), audit_sha256=sha(__file__),
        helper_sha256=sha(ROOT / 'scripts/audit_rv64m_contract.py'),
        checked_instructions=sum(stats['operations'] for item in outcomes.values()
                                 for stats in item['coverage'].values()),
        artifacts=artifacts, outcomes=outcomes, rejected_mutations=controls))
    print('PASS RV64I compute/control: 38 instruction forms and 38 rejected result/PC mutations',
          {name: row['coverage'][name]['operations'] for name, row in outcomes.items()})


if __name__ == '__main__':
    main()

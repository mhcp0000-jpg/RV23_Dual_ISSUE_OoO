"""Independently check finite RV64C compute, control and integer memory traces."""
import copy
import json

from audit_rv64i_compute_control import sx
from audit_rv64i_memory_values import initial_memory, inspect as inspect_memory
from audit_rv64m_contract import MASK
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, dump, sha, source_inputs


REQUIRED = set('''addi4spn addi16sp addi addiw li lui srli srai andi
    sub xor or and subw addw slli j beqz bnez jr jalr mv add nop'''.split())
MEMORY = {'c.' + name for name in ('lw', 'ld', 'sw', 'sd', 'lwsp', 'ldsp', 'swsp', 'sdsp')}


def decode(word, pc, registers):
    """Direct 16-bit field semantics; no DUT expander or expanded trace used."""
    if word & 3 == 3:
        return None
    assert 0 <= word <= 0xffff
    q, op = word & 3, word >> 13
    rd, rs2 = (word >> 7) & 31, (word >> 2) & 31
    rp, sp = 8 + ((word >> 7) & 7), 8 + ((word >> 2) & 7)
    imm = sx(((word >> 12) & 1) << 5 | ((word >> 2) & 31), 6)
    name, value, dest, target, taken = None, None, rd, pc + 2, None

    def reg(index):
        assert registers[index] is not None, (hex(pc), hex(word), index)
        return registers[index]

    if q in (0, 2) and op in (2, 3, 6, 7):
        return None  # All eight integer memory formats use the byte oracle.
    if q == 0 and op == 0:
        offset = (((word >> 7) & 15) << 6 | ((word >> 11) & 3) << 4
                  | ((word >> 5) & 1) << 3 | ((word >> 6) & 1) << 2)
        assert offset
        name, dest, value = 'addi4spn', sp, reg(2) + offset
    elif q == 1:
        if op == 0:
            name, value = ('nop' if rd == 0 and imm == 0 else 'addi'), reg(rd) + imm
        elif op == 1:
            assert rd
            name, value = 'addiw', sx(reg(rd) + imm, 32)
        elif op == 2:
            name, value = 'li', imm
        elif op == 3:
            if rd == 2:
                offset = sx(((word >> 12) & 1) << 9 | ((word >> 3) & 3) << 7
                            | ((word >> 5) & 1) << 6 | ((word >> 2) & 1) << 5
                            | ((word >> 6) & 1) << 4, 10)
                assert offset
                name, value = 'addi16sp', reg(2) + offset
            else:
                assert imm
                name, value = 'lui', imm << 12
        elif op == 4:
            mode, dest = (word >> 10) & 3, rp
            a = reg(rp)
            if mode < 2:
                shift = ((word >> 12) & 1) << 5 | ((word >> 2) & 31)
                name = 'srli' if mode == 0 else 'srai'
                value = a >> shift if mode == 0 else sx(a, 64) >> shift
            elif mode == 2:
                name, value = 'andi', a & imm
            else:
                code, b = (word >> 5) & 3, reg(sp)
                if word & 0x1000:
                    assert code < 2
                    name = ('subw', 'addw')[code]
                    value = sx(a - b if code == 0 else a + b, 32)
                else:
                    name = ('sub', 'xor', 'or', 'and')[code]
                    value = (a - b, a ^ b, a | b, a & b)[code]
        elif op == 5:
            offset = sx(((word >> 12) & 1) << 11 | ((word >> 8) & 1) << 10
                        | ((word >> 9) & 3) << 8 | ((word >> 6) & 1) << 7
                        | ((word >> 7) & 1) << 6 | ((word >> 2) & 1) << 5
                        | ((word >> 11) & 1) << 4 | ((word >> 3) & 7) << 1, 12)
            name, dest, target = 'j', 0, pc + offset
        elif op in (6, 7):
            offset = sx(((word >> 12) & 1) << 8 | ((word >> 5) & 3) << 6
                        | ((word >> 2) & 1) << 5 | ((word >> 10) & 3) << 3
                        | ((word >> 3) & 3) << 1, 9)
            name, dest = ('beqz' if op == 6 else 'bnez'), 0
            taken = (reg(rp) == 0) if op == 6 else (reg(rp) != 0)
            target = pc + offset if taken else pc + 2
    elif q == 2 and op == 0:
        name = 'slli'
        value = reg(rd) << (((word >> 12) & 1) << 5 | ((word >> 2) & 31))
    elif q == 2 and op == 4:
        if rs2:
            name = 'add' if word & 0x1000 else 'mv'
            value = reg(rs2) + (reg(rd) if name == 'add' else 0)
        else:
            assert rd, 'C.EBREAK/reserved is outside this successful-retirement oracle'
            name = 'jalr' if word & 0x1000 else 'jr'
            dest, value = (1, pc + 2) if name == 'jalr' else (0, None)
            target = reg(rd) & ~1
    assert name is not None, ('uncovered compressed encoding', hex(pc), hex(word))
    return name, dest, None if value is None else value & MASK, target & MASK, taken


def inspect(rows):
    registers, coverage = [None] * 32, {}
    registers[0] = 0
    for index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if pc >= 0x80000000 and word & 3 != 3:
            assert row['trap'] == '0', row
            item = decode(word, pc, registers)
            if item:
                name, rd, value, target, taken = item
                if rd and value is not None:
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                    assert int(row['wdata'], 16) == value, (name, row, hex(value))
                else:
                    assert row['rd_write'] == '0' or (row['rd_fp'] == '0' and row['rd'] == '0'), row
                assert index + 1 < len(rows)
                assert int(rows[index + 1]['pc'], 16) == target, (name, row, hex(target))
                stats = coverage.setdefault(name, dict(operations=0, checked_results=0, taken=0, not_taken=0))
                stats['operations'] += 1
                stats['checked_results'] += bool(rd and value is not None)
                if taken is not None:
                    stats['taken' if taken else 'not_taken'] += 1
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    return coverage


def main():
    path = ROOT / 'out/rva23/sail_upstream_comparison/report.json'
    base = json.loads(path.read_bytes())
    assert base['passed'] and source_inputs(base['inputs']) == base['inputs']
    model, reference = base['model'], base['reference']
    assert source_inputs(model['inputs']) == model['inputs']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    assert sha(ROOT / reference['binary']) == reference['binary_sha256']
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(model['params'])
    case = next(case for case in base['cases'] if case['name'] == 'rv64uc/rvc')
    assert case['reference_passed'] and case['rtl_passed']
    assert case['rtl_model_sha256'] == model['binary_sha256']
    assert case['reference_binary_sha256'] == reference['binary_sha256']
    artifacts = {}
    for key in ('elf', 'rtl_trace', 'sail_trace', 'sail_log'):
        assert sha(ROOT / case[key]) == case[key + '_sha256']
        artifacts[case[key]] = case[key + '_sha256']
    run = case['rtl']
    assert run['passed'] and run['exit_code'] == 0 and sha(ROOT / run['log']) == run['log_sha256']
    artifacts[run['log']] = run['log_sha256']
    actual = read_csv(ROOT / case['rtl_trace'])
    events, mismatch = compare(read_csv(ROOT / case['sail_trace']), actual)
    assert mismatch is None, mismatch
    coverage = inspect(actual)
    assert set(coverage) == REQUIRED, set(coverage) ^ REQUIRED
    for name in ('beqz', 'bnez'):
        assert coverage[name]['taken'] and coverage[name]['not_taken']
    memory = initial_memory(ROOT / case['elf'])
    memory_coverage = inspect_memory(actual, memory)
    assert MEMORY <= set(memory_coverage)
    for name in ('c.sw', 'c.sd', 'c.swsp', 'c.sdsp'):
        assert memory_coverage[name]['observed_stores'] > 0
    controls = []
    for name in sorted(REQUIRED):
        broken, registers = copy.deepcopy(actual), [None] * 32
        registers[0] = 0
        for index, row in enumerate(actual):
            word, pc = int(row['instruction'], 16), int(row['pc'], 16)
            item = decode(word, pc, registers) if pc >= 0x80000000 and row['trap'] == '0' else None
            if item and item[0] == name:
                if name in ('j', 'beqz', 'bnez', 'jr', 'jalr', 'nop'):
                    broken[index + 1]['pc'] = f"{int(broken[index + 1]['pc'], 16) ^ 2:016x}"
                else:
                    assert item[1] and item[2] is not None
                    broken[index]['wdata'] = f"{int(row['wdata'], 16) ^ 1:016x}"
                break
            if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
                registers[int(row['rd'])] = int(row['wdata'], 16)
        else:
            raise AssertionError(f'No mutation for {name}')
        try:
            inspect(broken)
        except AssertionError:
            controls.append(name)
        else:
            raise AssertionError(f'Incorrect C.{name} result/PC accepted')
    broken = copy.deepcopy(actual)
    row = next(row for row in broken if int(row['instruction'], 16) & 0xf07f == 0x9002
               and int(row['instruction'], 16) & 0xf80)
    row['wdata'] = f"{int(row['wdata'], 16) + 2:016x}"
    try:
        inspect(broken)
    except AssertionError:
        controls.append('jalr_link_pc_plus_four')
    else:
        raise AssertionError('Incorrect C.JALR PC+4 link accepted')
    memory_controls = []
    for name in sorted(MEMORY):
        broken = copy.deepcopy(actual)
        load = name.startswith(('c.lw', 'c.ld'))
        double, stack = name.startswith(('c.ld', 'c.sd')), name.endswith('sp')
        quadrant, op = (2 if stack else 0), (3 if double else 2) + (0 if load else 4)
        row = next(row for row in broken if int(row['pc'], 16) >= 0x80000000
                   and int(row['instruction'], 16) & 3 == quadrant
                   and int(row['instruction'], 16) >> 13 == op)
        if load:
            row['wdata'] = f"{int(row['wdata'], 16) ^ 1:016x}"
        else:
            # Alter an encoded address bit; later loads must expose wrong bytes.
            bit = (10 if double else 9) if stack else (5 if double else 6)
            row['instruction'] = f"{int(row['instruction'], 16) ^ (1 << bit):08x}"
        try:
            inspect_memory(broken, memory)
        except AssertionError:
            memory_controls.append(name)
        else:
            raise AssertionError(f'Incorrect C memory value/address accepted: {name}')
    dump(ROOT / 'out/rva23/rv64c_contract_audit.json', dict(passed=True,
        complete_profile_validation=False,
        scope='Finite upstream RV64C compute/control and eight integer memory formats; FP memory, illegal/hint encodings, all operands/immediates and scheduling separate',
        base_report_sha256=sha(path), audit_sha256=sha(__file__),
        audit_inputs=source_inputs(['scripts/audit_rv64i_compute_control.py',
            'scripts/audit_rv64i_memory_values.py', 'scripts/audit_rv64m_contract.py',
            'scripts/run_sail_event_comparison.py', 'scripts/sim_runner.py']),
        artifacts=artifacts, matched_events=events, coverage=coverage,
        memory_coverage=memory_coverage, rejected_result_or_pc_mutations=controls,
        rejected_memory_mutations=memory_controls))
    print('PASS RV64C:', len(coverage), 'compute/control forms;', events,
          'Sail/RTL events;', sum(item['operations'] for item in coverage.values()),
          'compressed compute/control retirements;', len(controls) + len(memory_controls),
          'rejected mutations', flush=True)


if __name__ == '__main__':
    main()

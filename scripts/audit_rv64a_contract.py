"""Finite bare-mode AMO/LR/SC byte-value audit; ordering is a separate gate."""
import copy
import json

from audit_rv64i_compute_control import sx
from audit_rv64i_memory_values import LOADS, STORES, expand_memory, initial_memory
from audit_rv64m_contract import MASK
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, dump, sha, source_inputs


AMO = {0: 'amoadd', 1: 'amoswap', 4: 'amoxor', 8: 'amoor', 12: 'amoand',
       16: 'amomin', 20: 'amomax', 24: 'amominu', 28: 'amomaxu'}
REQUIRED = {name + '_' + suffix for name in AMO.values() for suffix in ('w', 'd')}


def calculate(op, old, operand, bits):
    mask = (1 << bits) - 1
    a, b = old & mask, operand & mask
    if op == 0:
        value = a + b
    elif op == 1:
        value = b
    elif op in (4, 8, 12):
        value = {4: lambda: a ^ b, 8: lambda: a | b, 12: lambda: a & b}[op]()
    elif op in (16, 20):
        value = (min if op == 16 else max)(sx(a, bits), sx(b, bits))
    else:
        assert op in (24, 28)
        value = (min if op == 24 else max)(a, b)
    return value & mask


def inspect(rows, initial):
    registers, memory = [None] * 32, initial.copy()
    registers[0] = 0
    coverage, writers, writes = {}, {}, {}
    reservation = None
    for index, row in enumerate(rows):
        word, _ = expand_memory(int(row['instruction'], 16))
        opcode, f3, op = word & 127, (word >> 12) & 7, word >> 27
        pc = int(row['pc'], 16)
        if pc >= 0x80000000 and row['trap'] == '1':
            reservation = None
        if pc >= 0x80000000 and opcode in (3, 0x23, 0x2f):
            assert row['trap'] == '0', row
            rd, rs1, rs2 = (word >> 7) & 31, (word >> 15) & 31, (word >> 20) & 31
            base = registers[rs1]
            assert base is not None, row
            load, store, atomic = opcode == 3, opcode == 0x23, opcode == 0x2f
            if load:
                assert f3 in LOADS, row
                _, size, sign_extend = LOADS[f3]
                address = (base + sx(word >> 20, 12)) & MASK
            elif store:
                assert f3 in STORES, row
                _, size = STORES[f3]
                address = (base + sx((word >> 25) << 5 | (word >> 7) & 31, 12)) & MASK
            else:
                assert f3 in (2, 3) and op in (*AMO, 2, 3), row
                size, address = (4 if f3 == 2 else 8), base
                assert address % size == 0, row
                name = (AMO.get(op) or ('lr' if op == 2 else 'sc')) + ('_w' if size == 4 else '_d')
                stats = coverage.setdefault(name, dict(operations=0, checked_results=0,
                    zero_destination=0, high_word_operand=0, negative_old_word=0,
                    aqrl_encodings=[], sc_success=0, sc_failure=0, observed_writes=0,
                    fully_observed_writes=0))
                stats['operations'] += 1
                stats['zero_destination'] += rd == 0
                encoding = (word >> 25) & 3
                if encoding not in stats['aqrl_encodings']:
                    stats['aqrl_encodings'].append(encoding)
            addresses = [(address + offset) & MASK for offset in range(size)]
            value = None
            if load or atomic and op != 3:
                assert all(byte in memory for byte in addresses), (hex(address), row)
                old = sum(memory[byte] << (8 * i) for i, byte in enumerate(addresses))
                if load:
                    expected = (sx(old, size * 8) if sign_extend else old) & MASK
                    # Record only explicit later loads as write observation.
                    for byte in addresses:
                        if byte in writers:
                            writes[writers[byte]]['observed'].add(byte)
                else:
                    expected = sx(old, size * 8) & MASK
                    stats['negative_old_word'] += size == 4 and bool(old & (1 << 31))
                    if op == 2:
                        assert rs2 == 0, row
                        reservation = (address, size)
                    else:
                        operand = registers[rs2]
                        assert operand is not None, row
                        stats['high_word_operand'] += size == 4 and bool(operand >> 32)
                        value = calculate(op, old, operand, size * 8)
                        # An AMO uses the exclusive monitor in this implementation.
                        reservation = None
                if rd:
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                    assert int(row['wdata'], 16) == expected, (hex(address), hex(expected), row)
                    if atomic:
                        stats['checked_results'] += 1
            elif store:
                value = registers[rs2]
                assert value is not None, row
                if reservation and address // 64 == reservation[0] // 64:
                    reservation = None
            else:
                # Failure is allowed even with a reservation. A successful SC
                # must have a matching LR; success/failure memory is then checked
                # by subsequent ordinary loads. This does not prove progress.
                assert rd != 0 and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                success = int(row['wdata'], 16) == 0
                stats['checked_results'] += 1
                stats['sc_success' if success else 'sc_failure'] += 1
                if success:
                    assert reservation == (address, size), row
                    value = registers[rs2]
                    assert value is not None, row
                reservation = None
            if value is not None:
                if atomic:
                    writes[index] = dict(name=name, addresses=set(addresses), observed=set())
                for i, byte in enumerate(addresses):
                    memory[byte] = (value >> (8 * i)) & 255
                    if atomic:
                        writers[byte] = index
                    else:
                        writers.pop(byte, None)
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    for write in writes.values():
        coverage[write['name']]['observed_writes'] += bool(write['observed'])
        coverage[write['name']]['fully_observed_writes'] += write['observed'] == write['addresses']
    return coverage


def main():
    path = ROOT / 'out/rva23/sail_upstream_comparison/report.json'
    base = json.loads(path.read_bytes())
    assert base['passed'] and source_inputs(base['inputs']) == base['inputs']
    model, reference = base['model'], base['reference']
    assert source_inputs(model['inputs']) == model['inputs']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    assert reference['passed'] and sha(ROOT / reference['binary']) == reference['binary_sha256']
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(model['params'])
    cases = [case for case in base['cases'] if case['name'].startswith('rv64ua/')]
    assert len(cases) == 19 and {case['name'].split('/')[1] for case in cases} == REQUIRED | {'lrsc'}
    outcomes, artifacts, result_controls, memory_controls = {}, {}, [], []
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
        memory = initial_memory(ROOT / case['elf'])
        coverage = inspect(actual, memory)
        name = case['name'].split('/')[1]
        if name != 'lrsc':
            assert coverage[name]['operations'] > 0 and coverage[name]['fully_observed_writes'] > 0
            if name.endswith('_w'):
                assert coverage[name]['high_word_operand'] > 0
        else:
            assert coverage['lr_w']['operations'] > 0
            assert coverage['sc_w']['sc_success'] > 0 and coverage['sc_w']['sc_failure'] > 0
        outcomes[name] = dict(matched_events=events, coverage=coverage)
        for atomic_result, controls in ((True, result_controls), (False, memory_controls)):
            broken = copy.deepcopy(actual)
            row = next(row for row in broken if int(row['pc'], 16) >= 0x80000000
                       and expand_memory(int(row['instruction'], 16))[0] & 127 == (0x2f if atomic_result else 3)
                       and row['rd_write'] == '1' and int(row['rd']) != 0)
            row['wdata'] = f"{int(row['wdata'], 16) ^ 1:016x}"
            try:
                inspect(broken, memory)
            except AssertionError:
                controls.append(name)
            else:
                raise AssertionError(f'Incorrect {name} {atomic_result=} accepted')
    dump(ROOT / 'out/rva23/rv64a_contract_audit.json', dict(
        passed=True, complete_profile_validation=False,
        scope='Finite bare-mode AMO W/D and LR/SC W values; SC failures consumed as observed, no progress or concurrency proof; ordering/fault/guest tests separate',
        base_report_sha256=sha(path), model_binary_sha256=model['binary_sha256'],
        audit_inputs=source_inputs(['scripts/audit_rv64a_contract.py', 'scripts/audit_rv64i_memory_values.py',
            'scripts/audit_rv64i_compute_control.py', 'scripts/audit_rv64m_contract.py',
            'scripts/run_sail_event_comparison.py', 'scripts/sim_runner.py']),
        artifacts=artifacts, outcomes=outcomes, rejected_atomic_result_mutations=result_controls,
        rejected_load_mutations=memory_controls))
    print('PASS RV64A: 18 AMO forms and LR/SC.W;', len(result_controls),
          'atomic-result and', len(memory_controls), 'load-result mutations rejected')


if __name__ == '__main__':
    main()

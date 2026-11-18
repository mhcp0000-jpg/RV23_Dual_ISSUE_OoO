"""Reconstruct RV64M operands from retirement and check independent arithmetic."""
import copy
import json

from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, dump, sha, source_inputs


MASK = (1 << 64) - 1
OPS = {(0x33, i): name for i, name in enumerate(
    ('mul', 'mulh', 'mulhsu', 'mulhu', 'div', 'divu', 'rem', 'remu'))}
OPS.update({(0x3b, i): name for i, name in
            ((0, 'mulw'), (4, 'divw'), (5, 'divuw'), (6, 'remw'), (7, 'remuw'))})


def signed(value, width):
    return value - (1 << width) if value >> (width - 1) else value


def expected(name, a, b):
    width = 32 if name.endswith('w') else 64
    mask = (1 << width) - 1
    x, y = a & mask, b & mask
    if name.startswith('mul'):
        if name in ('mulh', 'mulhsu'):
            x = signed(x, 64)
        if name == 'mulh':
            y = signed(y, 64)
        result = x * y
        if name in ('mulh', 'mulhsu', 'mulhu'):
            result >>= 64
    else:
        if name in ('div', 'rem', 'divw', 'remw'):
            x, y = signed(x, width), signed(y, width)
        if y == 0:
            result = -1 if name.startswith('div') else x
        else:
            quotient = abs(x) // abs(y)
            if (x < 0) != (y < 0):
                quotient = -quotient
            result = quotient if name.startswith('div') else x - quotient * y
    result &= mask
    return (signed(result, 32) if width == 32 else result) & MASK


def inspect(rows):
    registers = [None] * 32
    registers[0] = 0
    coverage = {}
    for row in rows:
        word = int(row['instruction'], 16)
        key = (word & 0x7f, (word >> 12) & 7)
        if word >> 25 == 1 and key in OPS and int(row['pc'], 16) >= 0x80000000:
            name = OPS[key]
            a, b = registers[(word >> 15) & 31], registers[(word >> 20) & 31]
            assert a is not None and b is not None, (name, row)
            assert row['trap'] == '0', row
            rd = (word >> 7) & 31
            if rd:
                assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                assert int(row['wdata'], 16) == expected(name, a, b), (name, a, b, row)
            stats = coverage.setdefault(name, dict(operations=0, zero_divisor=0,
                signed_overflow=0, nonzero_upper_word_operands=0, zero_destination=0))
            stats['operations'] += 1
            stats['zero_destination'] += rd == 0
            width = 32 if name.endswith('w') else 64
            mask = (1 << width) - 1
            stats['zero_divisor'] += not name.startswith('mul') and b & mask == 0
            stats['signed_overflow'] += (name in ('div', 'rem', 'divw', 'remw')
                and a & mask == 1 << (width - 1) and b & mask == mask)
            stats['nonzero_upper_word_operands'] += width == 32 and (a >> 32 != 0 or b >> 32 != 0)
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0':
            rd = int(row['rd'])
            if rd:
                registers[rd] = int(row['wdata'], 16)
    return coverage


def main():
    path = ROOT / 'out/rva23/sail_upstream_comparison/report.json'
    base = json.loads(path.read_bytes())
    assert base['passed'] and source_inputs(base['inputs']) == base['inputs']
    model = base['model']
    assert source_inputs(model['inputs']) == model['inputs']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(model['params'])
    reference_model = base['reference']
    assert reference_model['passed'] and sha(ROOT / reference_model['binary']) == reference_model['binary_sha256']
    cases = [case for case in base['cases'] if case['name'].startswith('rv64um/')]
    assert {case['name'].split('/')[1] for case in cases} == set(OPS.values())
    outcomes, artifacts, controls = {}, {}, []
    for case in cases:
        assert case['reference_passed'] and case['rtl_passed']
        assert case['rtl_model_sha256'] == model['binary_sha256']
        assert case['reference_binary_sha256'] == reference_model['binary_sha256']
        step = case['rtl']
        assert step['passed'] and step['exit_code'] == 0
        assert sha(ROOT / step['log']) == step['log_sha256']
        artifacts[step['log']] = step['log_sha256']
        for key in ('elf', 'rtl_trace', 'sail_trace', 'sail_log'):
            assert sha(ROOT / case[key]) == case[key + '_sha256']
            artifacts[case[key]] = case[key + '_sha256']
        reference, actual = read_csv(ROOT / case['sail_trace']), read_csv(ROOT / case['rtl_trace'])
        events, mismatch = compare(reference, actual)
        assert mismatch is None, mismatch
        coverage = inspect(actual)
        name = case['name'].split('/')[1]
        assert name in coverage and coverage[name]['operations'] > 0
        if name.startswith(('div', 'rem')):
            assert coverage[name]['zero_divisor'] > 0
        if name in ('div', 'rem', 'divw', 'remw'):
            assert coverage[name]['signed_overflow'] > 0
        if name.endswith('w'):
            assert coverage[name]['nonzero_upper_word_operands'] > 0
        outcomes[name] = dict(matched_events=events, coverage=coverage)
        broken = copy.deepcopy(actual)
        index = next(i for i, row in enumerate(broken)
                     if (int(row['instruction'], 16) >> 25 == 1
                         and OPS.get((int(row['instruction'], 16) & 0x7f,
                                      (int(row['instruction'], 16) >> 12) & 7)) == name
                         and row['rd_write'] == '1' and int(row['rd']) != 0))
        broken[index]['wdata'] = f"{int(broken[index]['wdata'], 16) ^ 1:016x}"
        try:
            inspect(broken)
        except AssertionError:
            controls.append(name)
        else:
            raise AssertionError(f'Incorrect {name} result accepted')
    dump(ROOT / 'out/rva23/rv64m_contract_audit.json', dict(
        passed=True, complete_profile_validation=False,
        scope='RV64M 13-operation finite retirement evidence with independent arithmetic; not exhaustive operand/pipeline proof',
        base_report_sha256=sha(path), model_binary_sha256=model['binary_sha256'],
        audit_sha256=sha(__file__), artifacts=artifacts, outcomes=outcomes,
        rejected_result_mutations=controls))
    print('PASS RV64M: 13 operations, independent arithmetic and 13 rejected result mutations',
          {name: result['coverage'][name]['operations'] for name, result in outcomes.items()})


if __name__ == '__main__':
    main()

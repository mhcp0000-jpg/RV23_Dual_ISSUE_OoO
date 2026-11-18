"""Check finite RV64 Zba/Zbb/Zbs/Zicond retire evidence against integer rules."""
import copy
import json

from audit_rv64m_contract import MASK, signed
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, dump, sha, source_inputs


REQUIRED = set('''add_uw sh1add sh2add sh3add sh1add_uw sh2add_uw sh3add_uw slli_uw
    andn orn xnor clz clzw ctz ctzw cpop cpopw max maxu min minu orc_b rev8
    rol rolw ror rorw rori roriw sext_b sext_h zext_h
    bclr bclri bext bexti binv binvi bset bseti czero_eqz czero_nez'''.split())
GROUPS = ('rv64uzba/', 'rv64uzbb/', 'rv64uzbs/', 'rv64uzicond/')


def operation(word):
    op, f3, f7 = word & 127, (word >> 12) & 7, word >> 25
    rs2, imm = (word >> 20) & 31, word >> 20
    if op in (0x33, 0x3b):
        if f7 == 0x10 and f3 in (2, 4, 6):
            return f'sh{f3 // 2}add' + ('_uw' if op == 0x3b else '')
        if op == 0x3b and f7 == 4 and f3 == 0:
            return 'add_uw'
        if op == 0x3b and f7 == 4 and f3 == 4 and rs2 == 0:
            return 'zext_h'
        if f7 == 0x30 and f3 in (1, 5):
            return ('rol' if f3 == 1 else 'ror') + ('w' if op == 0x3b else '')
        if op == 0x33:
            return {(0x20, 7): 'andn', (0x20, 6): 'orn', (0x20, 4): 'xnor',
                (5, 4): 'min', (5, 5): 'minu', (5, 6): 'max', (5, 7): 'maxu',
                (0x24, 1): 'bclr', (0x24, 5): 'bext', (0x34, 1): 'binv',
                (0x14, 1): 'bset', (7, 5): 'czero_eqz', (7, 7): 'czero_nez'}.get((f7, f3))
    if op in (0x13, 0x1b):
        if f3 == 1 and imm in (0x600, 0x601, 0x602):
            return {0x600: 'clz', 0x601: 'ctz', 0x602: 'cpop'}[imm] + ('w' if op == 0x1b else '')
        if op == 0x1b and f3 == 5 and f7 == 0x30:
            return 'roriw'
        if op == 0x1b and f3 == 1 and word >> 26 == 2:
            return 'slli_uw'
        if op == 0x13:
            exact = {(1, 0x604): 'sext_b', (1, 0x605): 'sext_h',
                     (5, 0x287): 'orc_b', (5, 0x6b8): 'rev8'}
            if (f3, imm) in exact:
                return exact[f3, imm]
            return {(0x18, 5): 'rori', (0x12, 1): 'bclri', (0x12, 5): 'bexti',
                    (0x1a, 1): 'binvi', (0x0a, 1): 'bseti'}.get((word >> 26, f3))
    return None


def expected(name, a, b, word):
    width = 32 if name in ('clzw', 'ctzw', 'cpopw', 'rolw', 'rorw', 'roriw') else 64
    low = a & ((1 << width) - 1)
    shift = ((word >> 20) if name in ('rori', 'roriw', 'slli_uw', 'bclri', 'bexti', 'binvi', 'bseti') else b) & (width - 1)
    if name == 'add_uw':
        result = (a & 0xffffffff) + b
    elif name.startswith('sh'):
        result = ((a & 0xffffffff if name.endswith('_uw') else a) << int(name[2])) + b
    elif name == 'slli_uw':
        result = (a & 0xffffffff) << shift
    elif name in ('andn', 'orn', 'xnor'):
        result = {'andn': lambda: a & ~b, 'orn': lambda: a | ~b, 'xnor': lambda: ~(a ^ b)}[name]()
    elif name.startswith(('clz', 'ctz', 'cpop')):
        result = (width - low.bit_length() if name.startswith('clz') else
                  (low & -low).bit_length() - 1 if low and name.startswith('ctz') else
                  width if name.startswith('ctz') else low.bit_count())
    elif name in ('min', 'minu', 'max', 'maxu'):
        x, y = (a, b) if name.endswith('u') else (signed(a, 64), signed(b, 64))
        result = min(x, y) if name.startswith('min') else max(x, y)
    elif name == 'orc_b':
        result = sum((255 if (a >> (8 * i)) & 255 else 0) << (8 * i) for i in range(8))
    elif name == 'rev8':
        result = int.from_bytes(a.to_bytes(8, 'little'), 'big')
    elif name.startswith(('rol', 'ror')):
        bits = f'{low:0{width}b}'
        amount = shift if name.startswith('rol') else (-shift) % width
        result = int(bits[amount:] + bits[:amount], 2)
    elif name in ('sext_b', 'sext_h', 'zext_h'):
        size = 8 if name == 'sext_b' else 16
        result = a & ((1 << size) - 1)
        if name.startswith('sext'):
            result = signed(result, size)
    elif name.startswith(('bclr', 'bext', 'binv', 'bset')):
        bits = list(f'{a:064b}')
        index = 63 - shift
        if name.startswith('bext'):
            result = int(bits[index])
        else:
            bits[index] = '0' if name.startswith('bclr') else '1' if name.startswith('bset') else str(1 - int(bits[index]))
            result = int(''.join(bits), 2)
    else:
        assert name in ('czero_eqz', 'czero_nez'), name
        result = 0 if (b == 0 if name == 'czero_eqz' else b != 0) else a
    if width == 32:
        result = signed(result & 0xffffffff, 32)
    return result & MASK


def inspect(rows):
    registers, coverage = [None] * 32, {}
    registers[0] = 0
    for row in rows:
        word = int(row['instruction'], 16)
        name = operation(word)
        if name and int(row['pc'], 16) >= 0x80000000:
            assert row['trap'] == '0', row
            a = registers[(word >> 15) & 31]
            # Unary/immediate forms have no rs2 register dependency.
            b = registers[(word >> 20) & 31] if word & 127 in (0x33, 0x3b) else 0
            assert a is not None and b is not None, (name, row)
            rd = (word >> 7) & 31
            if rd:
                assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                assert int(row['wdata'], 16) == expected(name, a, b, word), (name, hex(a), hex(b), row)
            stats = coverage.setdefault(name, dict(operations=0, checked_results=0, zero_source=0, all_ones_source=0,
                source_high_bit=0, nonzero_upper_word=0, zero_second_operand=0, nonzero_second_operand=0,
                zero_destination=0))
            for key, value in dict(operations=1, checked_results=rd != 0, zero_source=a == 0, all_ones_source=a == MASK,
                source_high_bit=a >> 63 != 0, nonzero_upper_word=a >> 32 != 0,
                zero_second_operand=b == 0, nonzero_second_operand=b != 0, zero_destination=rd == 0).items():
                stats[key] += value
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    return coverage


def main():
    path = ROOT / 'out/rva23/sail_upstream_comparison/report.json'
    base = json.loads(path.read_bytes())
    assert base['passed'] and source_inputs(base['inputs']) == base['inputs']
    model, reference_model = base['model'], base['reference']
    assert source_inputs(model['inputs']) == model['inputs']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(model['params'])
    assert reference_model['passed'] and sha(ROOT / reference_model['binary']) == reference_model['binary_sha256']
    cases = [case for case in base['cases'] if case['name'].startswith(GROUPS)]
    assert len(cases) == len(REQUIRED) and {case['name'].split('/')[1] for case in cases} == REQUIRED
    outcomes, artifacts, controls = {}, {}, []
    for case in cases:
        assert case['reference_passed'] and case['rtl_passed']
        assert case['rtl_model_sha256'] == model['binary_sha256']
        assert case['reference_binary_sha256'] == reference_model['binary_sha256']
        step = case['rtl']
        assert step['passed'] and step['exit_code'] == 0 and sha(ROOT / step['log']) == step['log_sha256']
        artifacts[step['log']] = step['log_sha256']
        for key in ('elf', 'rtl_trace', 'sail_trace', 'sail_log'):
            assert sha(ROOT / case[key]) == case[key + '_sha256']
            artifacts[case[key]] = case[key + '_sha256']
        reference, actual = read_csv(ROOT / case['sail_trace']), read_csv(ROOT / case['rtl_trace'])
        events, mismatch = compare(reference, actual)
        assert mismatch is None, mismatch
        coverage = inspect(actual)
        name = case['name'].split('/')[1]
        assert name in coverage and coverage[name]['operations'] > 0, (name, coverage)
        if name in ('czero_eqz', 'czero_nez'):
            assert coverage[name]['zero_second_operand'] and coverage[name]['nonzero_second_operand']
        outcomes[name] = dict(matched_events=events, coverage=coverage)
        broken = copy.deepcopy(actual)
        index = next(i for i, row in enumerate(broken) if operation(int(row['instruction'], 16)) == name
                     and row['rd_write'] == '1' and int(row['rd']) != 0 and int(row['pc'], 16) >= 0x80000000)
        broken[index]['wdata'] = f"{int(broken[index]['wdata'], 16) ^ 1:016x}"
        try:
            inspect(broken)
        except AssertionError:
            controls.append(name)
        else:
            raise AssertionError(f'Incorrect {name} result accepted')
    # The upstream word-count traces lack nonzero upper-word inputs. Consume
    # the existing same-ELF H/V replay as a separate, non-Sail supplement.
    replay_path = ROOT / 'out/rva23/profile_hypervisor_replay/report.json'
    replay = json.loads(replay_path.read_bytes())
    assert replay['passed'] and source_inputs(replay['model']['inputs']) == replay['model']['inputs']
    assert sha(ROOT / replay['model']['binary']) == replay['model']['binary_sha256']
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(replay['model']['params'])
    assert source_inputs(replay['runtime_inputs']) == replay['runtime_inputs']
    assert replay['generator_sha256'] == sha(ROOT / 'scripts/run_profile_hypervisor_replay.py')
    supplement = next(case for case in replay['cases'] if case['name'] == 'scalar/bitmanip')
    assert supplement['passed'] and supplement['run']['passed'] and supplement['run']['exit_code'] == 0
    for key in ('elf', 'trace'):
        assert sha(ROOT / supplement[key]) == supplement[key + '_sha256']
        artifacts[supplement[key]] = supplement[key + '_sha256']
    step = supplement['run']
    assert sha(ROOT / step['log']) == step['log_sha256']
    artifacts[step['log']] = step['log_sha256']
    extra_rows = read_csv(ROOT / supplement['trace'])
    extra = inspect(extra_rows)
    assert set(extra) == REQUIRED
    for name in ('clzw', 'ctzw', 'cpopw'):
        assert extra[name]['nonzero_upper_word'] > 0 and extra[name]['zero_source'] > 0
    artifacts[replay_path.relative_to(ROOT).as_posix()] = sha(replay_path)
    dump(ROOT / 'out/rva23/rv64b_contract_audit.json', dict(
        passed=True, complete_profile_validation=False,
        scope='Finite RV64 Zba/Zbb/Zbs/Zicond retirement values with independent integer rules; not exhaustive encodings, operands or pipeline proof',
        base_report_sha256=sha(path), model_binary_sha256=model['binary_sha256'],
        audit_sha256=sha(__file__),
        audit_inputs=source_inputs(['scripts/audit_rv64b_contract.py', 'scripts/audit_rv64m_contract.py',
            'scripts/run_sail_event_comparison.py', 'scripts/sim_runner.py']),
        artifacts=artifacts, outcomes=outcomes,
        rejected_result_mutations=controls,
        supplemental_hv_replay=dict(name=supplement['name'], model_binary_sha256=replay['model']['binary_sha256'],
            source_inputs=replay['model']['inputs'], runtime_inputs=replay['runtime_inputs'],
            scope='Independent values from existing full H/V replay; no additional Sail comparison', coverage=extra)))
    print('PASS RV64 B/Zicond:', len(outcomes), 'forms,',
          sum(value['coverage'][name]['operations'] for name, value in outcomes.items()),
          'Sail/RTL retirements,', sum(value['coverage'][name]['checked_results'] for name, value in outcomes.items()),
          'checked destination values and', len(controls), 'rejected result mutations;',
          sum(value['operations'] for value in extra.values()), 'supplemental H/V results')


if __name__ == '__main__':
    main()

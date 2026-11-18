"""Exact-rational and identical-Sail-ELF F/D arithmetic on the native H/V SoC."""
import argparse
import copy
import json
from fractions import Fraction

from audit_hv_sail_fixture import check_fixture
from fp_reference import BinaryFP
from run_fp_bit_contract import BOX, unbox
from run_fp_integer_contract import labels
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/fp_arithmetic_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/fp_reference.py',
    'scripts/run_fp_integer_contract.py', 'scripts/run_fp_bit_contract.py',
    'scripts/audit_rv64i_compute_control.py', 'scripts/audit_rv64m_contract.py']
FMA = {'fmadd': 0x43, 'fmsub': 0x47, 'fnmsub': 0x4b, 'fnmadd': 0x4f}


def expected(case):
    fp = BinaryFP(8, 23) if case['width'] == 32 else BinaryFP(11, 52)
    a, b, c = (unbox(case[key], case['width']) for key in ('a', 'b', 'c'))
    op, rm = case['op'], case['rm']
    if op in ('fadd', 'fsub'):
        value, flags = fp.add(a, b, rm, op == 'fsub')
    elif op == 'fmul':
        value, flags = fp.multiply(a, b, rm)
    elif op == 'fdiv':
        value, flags = fp.divide(a, b, rm)
    elif op == 'fsqrt':
        value, flags = fp.sqrt(a, rm)
    else:
        assert op in FMA
        value, flags = fp.fused(a, b, c, rm, op in ('fnmsub', 'fnmadd'), op in ('fmsub', 'fnmadd'))
    return value | (BOX if case['width'] == 32 else 0), flags | case['fflags']


def cases(width, group):
    fp = BinaryFP(8, 23) if width == 32 else BinaryFP(11, 52)
    def number(value):
        return fp.pack(Fraction(value), 0)[0]
    one, two, three, four, half = (number(value) for value in (1, 2, 3, 4, Fraction(1, 2)))
    zero, negzero, tiny, normal, maximum = 0, fp.signbit, 1, 1 << fp.fb, fp.inf - 1
    minusone, qnan, snan = one | fp.signbit, fp.nan | 123, fp.inf | 123
    negqnan = qnan | fp.signbit
    ulp = Fraction(1, 1 << fp.fb)
    upper, lower, half_ulp = number(1 + ulp), number(1 - ulp), number(ulp / 2)
    if group == 'basic':
        add = [(zero, zero), (negzero, zero), (negzero, negzero), (one, minusone),
            (one, half_ulp), (one, half_ulp | fp.signbit), (minusone, half_ulp),
            (maximum, maximum), (maximum | fp.signbit, maximum | fp.signbit),
            (tiny, tiny), (normal, tiny), (fp.inf, fp.inf | fp.signbit),
            (fp.inf, fp.inf), (qnan, one), (snan, one), (negqnan, one)]
        multiply = [(zero, fp.inf), (fp.inf, zero), (one, zero), (minusone, zero),
            (negzero, minusone), (maximum, two), (maximum | fp.signbit, two),
            (tiny, half), (normal, half), (upper, upper), (qnan, one),
            (snan, one), (negqnan, one), (fp.inf, minusone)]
        divide = [(one, three), (minusone, three), (one, zero), (minusone, zero),
            (zero, zero), (fp.inf, fp.inf), (zero, one), (negzero, one),
            (one, fp.inf), (fp.inf, one), (tiny, two), (normal, three),
            (maximum, half), (qnan, one), (snan, one), (negqnan, one)]
        square_root = [zero, negzero, one, two, four, tiny, normal, maximum,
                       fp.inf, minusone, snan, qnan, negqnan]
        operands = {op: [(a, b, zero) for a, b in values] for op, values in
            [('fadd', add), ('fsub', add), ('fmul', multiply), ('fdiv', divide)]}
        operands['fsqrt'] = [(a, zero, zero) for a in square_root]
    else:
        assert group == 'fma'
        triples = [(upper, lower, minusone), (one, one, minusone),
            (zero, one, negzero), (negzero, one, zero), (maximum, two, zero),
            (maximum, two, maximum | fp.signbit), (tiny, half, zero),
            (normal, half, tiny | fp.signbit), (fp.inf, zero, qnan),
            (zero, fp.inf, qnan), (fp.inf, one, fp.inf | fp.signbit),
            (qnan, one, zero), (snan, one, zero), (negqnan, one, negzero), (one, one, tiny)]
        operands = {op: triples for op in FMA}
    result = []
    for op, triples in operands.items():
        for a, b, c in triples:
            for rm in range(5):
                for dynamic in (False, True):
                    word = (2 << 27 | 1 << 20 | 3 << 7 | FMA[op]) if op in FMA else {
                        'fadd': 0x001001d3, 'fsub': 0x081001d3, 'fmul': 0x101001d3,
                        'fdiv': 0x181001d3, 'fsqrt': 0x580001d3}[op]
                    word |= (width == 64) << 25 | (7 if dynamic else rm) << 12
                    result.append(dict(width=width, op=op,
                        a=a | (BOX if width == 32 else 0), b=b | (BOX if width == 32 else 0),
                        c=c | (BOX if width == 32 else 0), rm=rm, dynamic=dynamic,
                        frm=rm if dynamic else (rm + 1) % 5, fflags=5 if dynamic else 0, word=word))
    return result


def fixture(width, group):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6000', 'csrs mstatus,t0']
    for index, case in enumerate(cases(width, group), 1):
        value, flags = expected(case)
        lines += [f'li s0,{index}', f'li t0,{case["a"]:#x}', f'li t1,{case["b"]:#x}',
            f'li t2,{case["c"]:#x}', 'fmv.d.x ft0,t0', 'fmv.d.x ft1,t1', 'fmv.d.x ft2,t2',
            f'csrwi frm,{case["frm"]}', f'csrwi fflags,{case["fflags"]}',
            f'probe_{index}: .word {case["word"]:#x} # {case["op"]} width={width} rm={case["rm"]}',
            'fmv.x.d a0,ft3', f'li t2,{value:#x}', 'bne a0,t2,fail',
            f'flags_{index}: csrr a1,fflags', f'li t2,{flags}', 'bne a1,t2,fail']
    lines += ['li t1,1', 'j finish', 'fail:', 'slli t1,s0,1', 'ori t1,t1,1',
        'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt: j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, width, group, symbols):
    plan = cases(width, group)
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    flags = {symbols[f'flags_{i}']: expected(case)[1] for i, case in enumerate(plan, 1)}
    counts, seen, flag_reads, fp = {}, set(), set(), [None] * 32
    for row in rows:
        pc = int(row['pc'], 16)
        if pc >= 0x80000000:
            assert row['trap'] == '0', row
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and int(row['instruction'], 16) == case['word'], row
            assert fp[:3] == [case[key] for key in ('a', 'b', 'c')]
            assert row['rd_write'] == '1' and row['rd_fp'] == '1' and row['rd'] == '3'
            assert int(row['wdata'], 16) == expected(case)[0], (case, row)
            seen.add(pc)
            counts[case['op']] = counts.get(case['op'], 0) + 1
        if pc in flags:
            assert pc not in flag_reads and int(row['instruction'], 16) == 0x001025f3
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '11'
            assert int(row['wdata'], 16) == flags[pc], row
            flag_reads.add(pc)
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '1':
            fp[int(row['rd'])] = int(row['wdata'], 16)
    assert len(seen) == len(flag_reads) == len(plan)
    observed_flags = 0
    for case in plan:
        if not case['dynamic']:
            observed_flags |= expected(case)[1]
    assert observed_flags == (31 if group == 'basic' else 23)
    return dict(probes=len(plan), forms=counts, checked_fflags_reads=len(flag_reads),
        observed_static_flag_mask=observed_flags, static_rounding_modes=list(range(5)),
        dynamic_rounding_modes=list(range(5)), static_frm_deliberately_different=True)


def verifier(width, group, folder):
    def verify(sail_trace, rtl_trace):
        actual = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), actual)
        assert mismatch is None, mismatch
        symbols = labels(folder)
        result, controls = inspect(actual, width, group, symbols), []
        for op in result['forms']:
            index = next(i for i, case in enumerate(cases(width, group), 1) if case['op'] == op)
            for kind, bit in [('result', 1), ('NX', 1), ('UF', 2), ('OF', 4), ('DZ', 8), ('NV', 16)]:
                broken = copy.deepcopy(actual)
                pc = symbols[f'{"probe" if kind == "result" else "flags"}_{index}']
                row = next(row for row in broken if int(row['pc'], 16) == pc)
                row['wdata'] = f"{int(row['wdata'], 16) ^ bit:016x}"
                try:
                    inspect(broken, width, group, symbols)
                except AssertionError:
                    controls.append(dict(op=op, kind=kind))
                else:
                    raise AssertionError(f'Incorrect {op} {kind} accepted')
        if group == 'fma':
            case = cases(width, group)[0]
            fp = BinaryFP(8, 23) if width == 32 else BinaryFP(11, 52)
            a, b, c = (unbox(case[key], width) for key in ('a', 'b', 'c'))
            product, _ = fp.multiply(a, b, 0)
            split, _ = fp.add(product, c, 0)
            wrong = split | (BOX if width == 32 else 0)
            assert wrong != expected(case)[0]
            broken = copy.deepcopy(actual)
            row = next(row for row in broken if int(row['pc'], 16) == symbols['probe_1'])
            row['wdata'] = f'{wrong:016x}'
            try:
                inspect(broken, width, group, symbols)
            except AssertionError:
                controls.append(dict(op='fmadd', kind='split_rounding'))
            else:
                raise AssertionError('Split multiply/add rounding accepted')
            result['fused_rounding_witness'] = dict(fused=f'{expected(case)[0]:016x}', split=f'{wrong:016x}')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='Finite F/D arithmetic and fused rounding; all operands, reserved rm, FS permissions and pipeline races separate',
        inputs=source_inputs(DEPENDENCIES), cases=[])
    if args.check:
        saved = json.loads((FOLDER / 'report.json').read_bytes())
        assert saved['passed'] and saved['generator_sha256'] == top['generator_sha256']
        assert saved['inputs'] == top['inputs'] and len(saved['cases']) == 4
    else:
        dump(FOLDER / 'report.json', top)
    for width in (32, 64):
        for group in ('basic', 'fma'):
            folder = FOLDER / f'{width}_{group}'
            folder.mkdir(exist_ok=True)
            source, verify = folder / 'test.S', verifier(width, group, folder)
            if args.check:
                outcomes = check_fixture(folder, __file__, fixture(width, group), verify)
                old = next(case for case in saved['cases'] if (case['width'], case['group']) == (width, group))
                assert old['report_sha256'] == sha(folder / 'report.json') and old['outcomes'] == outcomes
            else:
                source.write_text(fixture(width, group), encoding='utf-8')
                outcomes = run_fixture(source, folder, __file__, verify,
                    source_dependencies=DEPENDENCIES, timeout_cycles=2000000)
            top['cases'].append(dict(width=width, group=group, report_sha256=sha(folder / 'report.json'), outcomes=outcomes))
            if not args.check:
                dump(FOLDER / 'report.json', top)
            print('PASS native FP arithmetic', width, group, outcomes['probes'], 'probes;',
                  outcomes['matched_events'], 'Sail/RTL events;', len(outcomes['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

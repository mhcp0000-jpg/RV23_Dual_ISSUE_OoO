"""Native H/V and identical Sail ELFs for the RV64 S/D Zfa instruction forms."""
import argparse
import copy
import json
from fractions import Fraction

from audit_hv_sail_fixture import check_fixture
from fp_reference import BinaryFP, round_int
from run_fp_bit_contract import BOX, MASK, unbox
from run_fp_integer_contract import labels
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/zfa_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/fp_reference.py',
    'scripts/run_fp_integer_contract.py', 'scripts/run_fp_bit_contract.py',
    'scripts/audit_rv64i_compute_control.py', 'scripts/audit_rv64m_contract.py']
FLI = [-1, 'min', Fraction(1, 65536), Fraction(1, 32768), Fraction(1, 256),
    Fraction(1, 128), Fraction(1, 16), Fraction(1, 8), Fraction(1, 4), Fraction(5, 16),
    Fraction(3, 8), Fraction(7, 16), Fraction(1, 2), Fraction(5, 8), Fraction(3, 4),
    Fraction(7, 8), 1, Fraction(5, 4), Fraction(3, 2), Fraction(7, 4), 2, Fraction(5, 2),
    3, 4, 8, 16, 128, 256, 32768, 65536, 'inf', 'nan']


def expected(case):
    fp = BinaryFP(8, 23) if case['width'] == 32 else BinaryFP(11, 52)
    a, b = unbox(case['a'], case['width']), unbox(case['b'], case['width'])
    name, flags = case['name'], 0
    if name == 'fli':
        value = FLI[case['index']]
        value = (1 << fp.fb) if value == 'min' else fp.inf if value == 'inf' else fp.nan if value == 'nan' else fp.pack(Fraction(value), 0)[0]
    elif name in ('fminm', 'fmaxm'):
        value, flags = fp.minmax(a, b, name == 'fmaxm', True)
    elif name in ('fltq', 'fleq'):
        value, flags = fp.compare(a, b, 'lt' if name == 'fltq' else 'le', True)
    elif name in ('fround', 'froundnx'):
        if fp.is_nan(a):
            value, flags = fp.nan, 16 if fp.is_snan(a) else 0
        elif fp.is_inf(a) or fp.is_zero(a):
            value = a
        else:
            exact = fp.value(a)
            integer, inexact = round_int(abs(exact).numerator, abs(exact).denominator, exact < 0, case['rm'])
            integer = -integer if exact < 0 else integer
            value, _ = fp.pack(Fraction(integer), case['rm'], fp.sign(a))
            flags = int(name == 'froundnx' and inexact)
    else:
        assert name == 'fcvtmod'
        _, flags = fp.to_int(a, 32, False, 1)
        if fp.is_nan(a) or fp.is_inf(a):
            integer = 0
        else:
            exact = fp.value(a)
            integer = abs(exact.numerator) // exact.denominator
            integer = -integer if exact < 0 else integer
        value = integer & 0xffffffff
        if value & 0x80000000:
            value |= 0xffffffff00000000
    if case['fp'] and case['width'] == 32:
        value |= BOX
    return value, flags | case['fflags']


def cases(width):
    fp = BinaryFP(8, 23) if width == 32 else BinaryFP(11, 52)
    box = BOX if width == 32 else 0
    def number(value):
        return fp.pack(Fraction(value), 0)[0] | box
    zero, minuszero, one, minusone = box, fp.signbit | box, number(1), number(-1)
    qnan, snan = fp.nan | 123 | box, fp.inf | 123 | box
    raw = [zero, minuszero, 1 | box, fp.signbit | 1 | box,
        *[number(value) for value in (Fraction(1, 2), Fraction(-1, 2), Fraction(3, 2),
            Fraction(-3, 2), Fraction(5, 2), Fraction(-5, 2))], one, fp.inf - 1 | box,
        fp.inf | box, fp.inf | fp.signbit | box, qnan, snan, qnan | fp.signbit, snan | fp.signbit]
    if width == 32:
        raw += [0x000000003f800000, 0x12345678ff800123]
    pairs = [(zero, minuszero), (minuszero, zero), (one, minusone), (minusone, one),
        (fp.inf | box, one), (one, fp.inf | box), (qnan, one), (one, qnan),
        (snan, one), (one, snan), (qnan, snan), (snan, qnan), (qnan, qnan),
        (snan, snan), (qnan | fp.signbit, one), (snan | fp.signbit, one)]
    if width == 32:
        pairs += [(0x3f800000, one), (one, 0xff800123), (0x3f800000, 0xff800123)]
    result = []
    def add(name, word, a, b=zero, *, integer=False, index=None, rm=0, dynamic=False, flags=0):
        result.append(dict(name=name, width=width, word=word | (width == 64) << 25,
            a=a, b=b, fp=not integer, index=index, rm=rm, dynamic=dynamic,
            frm=rm if dynamic else (rm + 1) % 5, fflags=flags))
    for index in range(32):
        for flags, frm in ((0, 0), (5, 5), (31, 7)):
            add('fli', 0xf0100153 | index << 15, zero, index=index, flags=flags)
            result[-1]['frm'] = frm
    for name, word in [('fminm', 0x28102153), ('fmaxm', 0x28103153),
                       ('fltq', 0xa0105553), ('fleq', 0xa0104553)]:
        for a, b in pairs:
            for flags, frm in ((0, 0), (5, 5), (31, 7)):
                add(name, word, a, b, integer=name in ('fltq', 'fleq'), flags=flags)
                result[-1]['frm'] = frm
    for name, selector in [('fround', 4), ('froundnx', 5)]:
        for a in raw:
            for rm in range(5):
                for dynamic in (False, True):
                    add(name, 0x40000153 | selector << 20 | (7 if dynamic else rm) << 12,
                        a, rm=rm, dynamic=dynamic, flags=5 if dynamic else 0)
    if width == 64:
        modular = [*raw, *[number(value) for value in [1 << 31, -(1 << 31), 1 << 32,
            Fraction(2 * (1 << 32) + 3, 2), Fraction(-2 * (1 << 32) - 3, 2), 1 << 63, 1 << 64]]]
        for a in dict.fromkeys(modular):
            for flags, frm in ((0, 0), (5, 5), (31, 7)):
                add('fcvtmod', 0xc2801553, a, integer=True, rm=1, flags=flags)
                result[-1]['frm'] = frm
    return result


def fixture(width):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6000', 'csrs mstatus,t0']
    for index, case in enumerate(cases(width), 1):
        value, flags = expected(case)
        lines += [f'li s0,{index}', f'li t0,{case["a"]:#x}', f'li t1,{case["b"]:#x}',
            'fmv.d.x ft0,t0', 'fmv.d.x ft1,t1', f'li t2,{value ^ MASK:#x}', 'fmv.d.x ft2,t2',
            f'li a0,{value ^ MASK:#x}', f'csrwi frm,{case["frm"]}', f'csrwi fflags,{case["fflags"]}',
            f'probe_{index}: .word {case["word"]:#x} # {case["name"]}']
        if case['fp']:
            lines.append('fmv.x.d a0,ft2')
        lines += [f'li t2,{value:#x}', 'bne a0,t2,fail', f'flags_{index}: csrr a1,fflags',
            f'li t2,{flags}', 'bne a1,t2,fail']
    lines += ['li t1,1', 'j finish', 'fail:', 'slli t1,s0,1', 'ori t1,t1,1',
        'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt: j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, width, symbols):
    plan = cases(width)
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    flags = {symbols[f'flags_{i}']: expected(case)[1] for i, case in enumerate(plan, 1)}
    counts, seen, flag_reads, indices = {}, set(), set(), set()
    fp, registers = [None] * 32, [None] * 32
    registers[0] = 0
    for row in rows:
        pc = int(row['pc'], 16)
        if pc >= 0x80000000:
            assert row['trap'] == '0', row
        if pc in probes:
            case = probes[pc]
            value, _ = expected(case)
            assert pc not in seen and int(row['instruction'], 16) == case['word']
            assert fp[0:2] == [case['a'], case['b']]
            assert (fp[2] if case['fp'] else registers[10]) == value ^ MASK
            assert row['rd_write'] == '1' and int(row['rd_fp']) == case['fp']
            assert int(row['rd']) == (2 if case['fp'] else 10)
            assert int(row['wdata'], 16) == value, (case, row)
            seen.add(pc)
            counts[case['name']] = counts.get(case['name'], 0) + 1
            if case['name'] == 'fli':
                indices.add(case['index'])
        if pc in flags:
            assert pc not in flag_reads and int(row['instruction'], 16) == 0x001025f3
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '11'
            assert int(row['wdata'], 16) == flags[pc], row
            flag_reads.add(pc)
        if row['trap'] == '0' and row['rd_write'] == '1':
            rd, value = int(row['rd']), int(row['wdata'], 16)
            if row['rd_fp'] == '1':
                fp[rd] = value
            elif rd:
                registers[rd] = value
    assert len(seen) == len(flag_reads) == len(plan) and indices == set(range(32))
    return dict(probes=len(plan), forms=counts, checked_fflags_reads=len(flag_reads),
        fli_indices=sorted(indices), static_rounding_modes=list(range(5)), dynamic_rounding_modes=list(range(5)))


def verifier(width, folder):
    def verify(sail_trace, rtl_trace):
        actual = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), actual)
        assert mismatch is None, mismatch
        symbols = labels(folder)
        result, controls = inspect(actual, width, symbols), []
        for name in result['forms']:
            index = next(i for i, case in enumerate(cases(width), 1) if case['name'] == name)
            for kind, bit in [('result', 1), ('NX', 1), ('NV', 16)]:
                broken = copy.deepcopy(actual)
                pc = symbols[f'{"probe" if kind == "result" else "flags"}_{index}']
                row = next(row for row in broken if int(row['pc'], 16) == pc)
                row['wdata'] = f"{int(row['wdata'], 16) ^ bit:016x}"
                try:
                    inspect(broken, width, symbols)
                except AssertionError:
                    controls.append(dict(name=name, kind=kind))
                else:
                    raise AssertionError(f'Incorrect {name} {kind} accepted')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='Finite RV64 S/D Zfa forms with exact bit/rational oracle and identical Sail ELFs; optional H/Q/RV32 forms, reserved rm and all scheduling/permission combinations separate',
        inputs=source_inputs(DEPENDENCIES), cases=[])
    if args.check:
        saved = json.loads((FOLDER / 'report.json').read_bytes())
        assert saved['passed'] and saved['generator_sha256'] == top['generator_sha256']
        assert saved['inputs'] == top['inputs'] and len(saved['cases']) == 2
    else:
        dump(FOLDER / 'report.json', top)
    for width in (32, 64):
        folder = FOLDER / str(width)
        folder.mkdir(exist_ok=True)
        source, verify = folder / 'test.S', verifier(width, folder)
        if args.check:
            outcomes = check_fixture(folder, __file__, fixture(width), verify)
            old = next(case for case in saved['cases'] if case['width'] == width)
            assert old['report_sha256'] == sha(folder / 'report.json') and old['outcomes'] == outcomes
        else:
            source.write_text(fixture(width), encoding='utf-8')
            outcomes = run_fixture(source, folder, __file__, verify,
                source_dependencies=DEPENDENCIES, timeout_cycles=2000000)
        top['cases'].append(dict(width=width, report_sha256=sha(folder / 'report.json'), outcomes=outcomes))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS native Zfa', width, outcomes['probes'], 'probes;',
            outcomes['matched_events'], 'Sail/RTL events;', len(outcomes['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

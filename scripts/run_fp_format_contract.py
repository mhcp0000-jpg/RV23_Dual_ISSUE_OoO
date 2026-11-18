"""Native H/V and identical Sail ELFs for S/D/H conversion boundaries."""
import argparse
import copy
import json
from fractions import Fraction

from audit_hv_sail_fixture import check_fixture
from fp_reference import BinaryFP
from run_fp_integer_contract import labels
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/fp_format_contract'
FORMATS = {0: BinaryFP(8, 23), 1: BinaryFP(11, 52), 2: BinaryFP(5, 10)}
NAMES = {0: 's', 1: 'd', 2: 'h'}
MASK = (1 << 64) - 1
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/fp_reference.py',
    'scripts/run_fp_integer_contract.py', 'scripts/run_fp_bit_contract.py',
    'scripts/audit_rv64i_compute_control.py', 'scripts/audit_rv64m_contract.py']


def power2(exponent):
    return Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)


def box(value, fp):
    return value | (MASK ^ fp.mask)


def expected(case):
    src, dst = FORMATS[case['source']], FORMATS[case['destination']]
    raw = case['a']
    a = src.nan if raw >> src.width != MASK >> src.width else raw & src.mask
    value, flags = dst.convert(a, src, case['rm'])
    return box(value, dst), flags | case['fflags']


def cases(destination):
    dst = FORMATS[destination]
    result = []
    for source, src in FORMATS.items():
        if source == destination:
            continue
        raw = [0, src.signbit, 1, src.signbit | 1, src.fracmask,
            1 << src.fb, src.inf - 1, src.signbit | (src.inf - 1),
            src.inf, src.signbit | src.inf, src.nan | 123, src.inf | 123,
            src.pack(Fraction(1), 0)[0], src.pack(Fraction(-1), 0)[0]]
        if src.width > dst.width:
            tiny = power2(dst.emin - dst.fb)
            normal = power2(dst.emin)
            maximum = (2 - power2(-dst.fb)) * power2(dst.emax)
            half_ulp = power2(dst.emax - dst.fb - 1)
            center = 1 + power2(-dst.fb - 1)
            epsilon = power2(-src.fb)
            points = [tiny / 2, 3 * tiny / 2, normal - tiny / 2, normal - tiny / 4,
                maximum, maximum + half_ulp / 2, maximum + half_ulp, power2(dst.emax + 1),
                center, center - epsilon, center + epsilon]
            for value in points:
                raw += [src.pack(value, 0)[0], src.pack(-value, 0)[0]]
        raw = list(dict.fromkeys(box(value, src) for value in raw))
        if source == 0:
            raw += [0x000000003f800000, 0x12345678ff800123]
        elif source == 2:
            raw += [0x0000000000003c00, 0xffffffff00007c01, 0x123456789abcfc01]
        for a in raw:
            for rm in range(5):
                for dynamic in (False, True):
                    word = 0x40000153 | destination << 25 | source << 20
                    word |= (7 if dynamic else rm) << 12
                    result.append(dict(name=f'{NAMES[source]}_to_{NAMES[destination]}',
                        source=source, destination=destination, a=a, rm=rm, dynamic=dynamic,
                        frm=rm if dynamic else (rm + 1) % 5, fflags=5 if dynamic else 0, word=word))
    return result


def fixture(destination):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6000', 'csrs mstatus,t0']
    for index, case in enumerate(cases(destination), 1):
        value, flags = expected(case)
        lines += [f'li s0,{index}', f'li t0,{case["a"]:#x}', 'fmv.d.x ft0,t0',
            f'csrwi frm,{case["frm"]}', f'csrwi fflags,{case["fflags"]}',
            f'probe_{index}: .word {case["word"]:#x} # {case["name"]} rm={case["rm"]}',
            'fmv.x.d a0,ft2', f'li t2,{value:#x}', 'bne a0,t2,fail',
            f'flags_{index}: csrr a1,fflags', f'li t2,{flags}', 'bne a1,t2,fail']
    lines += ['li t1,1', 'j finish', 'fail:', 'slli t1,s0,1', 'ori t1,t1,1',
        'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt: j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, destination, symbols):
    plan = cases(destination)
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    flags = {symbols[f'flags_{i}']: expected(case)[1] for i, case in enumerate(plan, 1)}
    counts, seen, flag_reads, fp = {}, set(), set(), [None] * 32
    for row in rows:
        pc = int(row['pc'], 16)
        if pc >= 0x80000000:
            assert row['trap'] == '0', row
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and int(row['instruction'], 16) == case['word']
            assert fp[0] == case['a']
            assert row['rd_write'] == '1' and row['rd_fp'] == '1' and row['rd'] == '2'
            assert int(row['wdata'], 16) == expected(case)[0], (case, row)
            seen.add(pc)
            counts[case['name']] = counts.get(case['name'], 0) + 1
        if pc in flags:
            assert pc not in flag_reads and int(row['instruction'], 16) == 0x001025f3
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '11'
            assert int(row['wdata'], 16) == flags[pc], row
            flag_reads.add(pc)
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '1':
            fp[int(row['rd'])] = int(row['wdata'], 16)
    assert len(seen) == len(flag_reads) == len(plan)
    return dict(probes=len(plan), forms=counts, checked_fflags_reads=len(flag_reads),
        static_rounding_modes=list(range(5)), dynamic_rounding_modes=list(range(5)),
        static_frm_deliberately_different=True)


def verifier(destination, folder):
    def verify(sail_trace, rtl_trace):
        actual = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), actual)
        assert mismatch is None, mismatch
        symbols = labels(folder)
        result, controls = inspect(actual, destination, symbols), []
        for name in result['forms']:
            index = next(i for i, case in enumerate(cases(destination), 1) if case['name'] == name)
            for kind, bit in (('result', 1), ('NX', 1), ('UF', 2), ('OF', 4), ('NV', 16)):
                broken = copy.deepcopy(actual)
                pc = symbols[f'{"probe" if kind == "result" else "flags"}_{index}']
                row = next(row for row in broken if int(row['pc'], 16) == pc)
                row['wdata'] = f"{int(row['wdata'], 16) ^ bit:016x}"
                try:
                    inspect(broken, destination, symbols)
                except AssertionError:
                    controls.append(dict(name=name, kind=kind))
                else:
                    raise AssertionError(f'Incorrect {name} {kind} accepted')
        if destination == 2:
            index, case = next((i, case) for i, case in enumerate(cases(destination), 1)
                if case['source'] == 1 and case['a'] == 0x3ff0020000000001
                and case['rm'] == 0 and not case['dynamic'])
            middle, _ = FORMATS[0].convert(case['a'], FORMATS[1], 0)
            indirect, _ = FORMATS[2].convert(middle, FORMATS[0], 0)
            wrong = box(indirect, FORMATS[2])
            assert wrong != expected(case)[0]
            broken = copy.deepcopy(actual)
            row = next(row for row in broken if int(row['pc'], 16) == symbols[f'probe_{index}'])
            row['wdata'] = f'{wrong:016x}'
            try:
                inspect(broken, destination, symbols)
            except AssertionError:
                controls.append(dict(name=case['name'], kind='double_rounding'))
            else:
                raise AssertionError('D-to-S-to-H double rounding accepted')
            result['direct_rounding_witness'] = dict(input=f'{case["a"]:016x}',
                direct=f'{expected(case)[0]:016x}', via_single=f'{wrong:016x}')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='Finite S/D/H conversions with exact rational oracle and identical Sail ELFs; arithmetic, half memory/moves, reserved rm and FS/pipeline races separate',
        inputs=source_inputs(DEPENDENCIES), cases=[])
    if args.check:
        saved = json.loads((FOLDER / 'report.json').read_bytes())
        assert saved['passed'] and saved['generator_sha256'] == top['generator_sha256']
        assert saved['inputs'] == top['inputs'] and len(saved['cases']) == 3
    else:
        dump(FOLDER / 'report.json', top)
    for destination in FORMATS:
        folder = FOLDER / NAMES[destination]
        folder.mkdir(exist_ok=True)
        source, verify = folder / 'test.S', verifier(destination, folder)
        if args.check:
            outcomes = check_fixture(folder, __file__, fixture(destination), verify)
            old = next(case for case in saved['cases'] if case['destination'] == destination)
            assert old['report_sha256'] == sha(folder / 'report.json') and old['outcomes'] == outcomes
        else:
            source.write_text(fixture(destination), encoding='utf-8')
            outcomes = run_fixture(source, folder, __file__, verify,
                source_dependencies=DEPENDENCIES, timeout_cycles=2000000)
        top['cases'].append(dict(destination=destination, report_sha256=sha(folder / 'report.json'), outcomes=outcomes))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS native FP format conversion to', NAMES[destination], outcomes['probes'], 'probes;',
              outcomes['matched_events'], 'Sail/RTL events;', len(outcomes['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

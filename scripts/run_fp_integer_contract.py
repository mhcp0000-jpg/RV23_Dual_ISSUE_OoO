"""Native H/V and pinned Sail integer/FP conversions using exact rationals."""
import argparse
import copy
import json
import subprocess
from fractions import Fraction

from audit_hv_sail_fixture import check_fixture
from audit_rv64i_compute_control import sx
from fp_reference import BinaryFP
from run_fp_bit_contract import BOX, MASK, unbox
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/fp_integer_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/fp_reference.py',
    'scripts/run_fp_bit_contract.py', 'scripts/audit_rv64i_compute_control.py', 'scripts/audit_rv64m_contract.py']


def expected(case):
    fp = BinaryFP(8, 23) if case['width'] == 32 else BinaryFP(11, 52)
    bits = 32 if case['selector'] < 2 else 64
    unsigned = bool(case['selector'] & 1)
    if case['to_int']:
        value, flags = fp.to_int(unbox(case['a'], case['width']), bits, unsigned, case['rm'])
        value = sx(value, 32) & MASK if bits == 32 else value & MASK
    else:
        value, flags = fp.from_int(case['a'], bits, unsigned, case['rm'])
        if case['width'] == 32:
            value |= BOX
    return value, flags | case['fflags']


def cases(width):
    fp = BinaryFP(8, 23) if width == 32 else BinaryFP(11, 52)
    floating = [0, fp.signbit, *[fp.pack(value, 0)[0] for value in
        [Fraction(1, 2), Fraction(-1, 2), Fraction(3, 2), Fraction(-3, 2), Fraction(5, 2)]]]
    for power in (31, 32, 63, 64):
        value = fp.pack(Fraction(1 << power), 0)[0]
        floating += [value - 1, value, value | fp.signbit]
    floating += [fp.inf, fp.inf | fp.signbit, fp.nan | 123, fp.inf | 123]
    floating = list(dict.fromkeys(value | (BOX if width == 32 else 0) for value in floating))
    if width == 32:
        floating += [0x123456783f800000]
    integer = [0, 1, MASK, 1 << 31, 0xdeadbeef00000001, (1 << 63) - 1,
               1 << 63, 0xffffffff80000001, (1 << 24) + 1, (1 << 24) + 3, (1 << 53) + 1]
    result = []
    for to_int, values in ((True, floating), (False, integer)):
        for selector, kind in enumerate(('w', 'wu', 'l', 'lu')):
            for a in values:
                for rm in range(5):
                    for dynamic in (False, True):
                        name = f'{"to" if to_int else "from"}_{kind}_{width}'
                        word = (0xc0000553 if to_int else 0xd0028153) | selector << 20
                        word |= (width == 64) << 25 | (7 if dynamic else rm) << 12
                        result.append(dict(name=name, width=width, to_int=to_int, selector=selector,
                            a=a, rm=rm, dynamic=dynamic, frm=rm if dynamic else (rm + 1) % 5,
                            fflags=5 if dynamic else 0, word=word))
    return result


def fixture(width):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6000', 'csrs mstatus,t0']
    for index, case in enumerate(cases(width), 1):
        value, flags = expected(case)
        lines += [f'li s0,{index}', f'li t0,{case["a"]:#x}', 'fmv.d.x ft0,t0',
            f'csrwi frm,{case["frm"]}', f'csrwi fflags,{case["fflags"]}',
            f'probe_{index}: .word {case["word"]:#x} # {case["name"]} rm={case["rm"]} dynamic={case["dynamic"]}']
        if not case['to_int']:
            lines.append('fmv.x.d a0,ft2')
        lines += [f'li t2,{value:#x}', 'bne a0,t2,fail', f'flags_{index}: csrr a1,fflags',
                  f'li t2,{flags}', 'bne a1,t2,fail']
    lines += ['li t1,1', 'j finish', 'fail:', 'slli t1,s0,1', 'ori t1,t1,1',
        'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt: j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def labels(folder):
    text = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
    return {parts[2]: int(parts[0], 16) for line in text.splitlines() if len(parts := line.split()) == 3}


def inspect(rows, width, symbols):
    plan = cases(width)
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    flags = {symbols[f'flags_{i}']: expected(case)[1] for i, case in enumerate(plan, 1)}
    counts, seen, flag_reads = {}, set(), set()
    fp, registers = [None] * 32, [None] * 32
    registers[0] = 0
    for row in rows:
        pc = int(row['pc'], 16)
        if pc >= 0x80000000:
            assert row['trap'] == '0', row
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and int(row['instruction'], 16) == case['word'], row
            assert (fp[0] if case['to_int'] else registers[5]) == case['a']
            seen.add(pc)
            assert row['rd_write'] == '1' and int(row['rd_fp']) == int(not case['to_int'])
            assert int(row['rd']) == (10 if case['to_int'] else 2)
            assert int(row['wdata'], 16) == expected(case)[0], (case, row)
            counts[case['name']] = counts.get(case['name'], 0) + 1
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
    assert len(seen) == len(flag_reads) == len(plan)
    return dict(probes=len(plan), forms=counts, checked_fflags_reads=len(flag_reads),
        static_rounding_modes=list(range(5)), dynamic_rounding_modes=list(range(5)),
        static_frm_deliberately_different=True)


def verifier(width, folder):
    def verify(sail_trace, rtl_trace):
        actual = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), actual)
        assert mismatch is None, mismatch
        symbols = labels(folder)
        result = inspect(actual, width, symbols)
        controls = []
        for name in result['forms']:
            index = next(i for i, case in enumerate(cases(width), 1) if case['name'] == name)
            for kind, bit in (('result', 1), ('NX', 1), ('NV', 16)):
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
        scope='Finite integer/FP conversions with exact rational oracle and Sail; FP format conversions, arithmetic, reserved rm and FS permissions separate',
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
        print('PASS native FP integer conversions', width, outcomes['probes'], 'probes;',
              outcomes['matched_events'], 'Sail/RTL events;', len(outcomes['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

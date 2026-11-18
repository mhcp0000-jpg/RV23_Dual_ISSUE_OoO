"""Independent finite F/D compare/min/max values and accrued NV on native H/V."""
import argparse
import copy
import json
import subprocess

from run_fp_bit_contract import BOX, unbox
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/fp_compare_contract'


def nan(value, width):
    fraction_bits, exponent_bits = (23, 8) if width == 32 else (52, 11)
    fraction = value & ((1 << fraction_bits) - 1)
    is_nan = ((value >> fraction_bits) & ((1 << exponent_bits) - 1)) == (1 << exponent_bits) - 1 and fraction != 0
    return is_nan, is_nan and not bool(fraction & (1 << (fraction_bits - 1)))


def expected(case):
    width, name = case['width'], case['name']
    a, b = unbox(case['a'], width), unbox(case['b'], width)
    an, ass = nan(a, width)
    bn, bs = nan(b, width)
    magnitude_mask = (1 << (width - 1)) - 1
    def rank(value):
        magnitude = value & magnitude_mask
        return -magnitude if value >> (width - 1) else magnitude
    if name in ('feq', 'flt', 'fle'):
        invalid = (ass or bs) if name == 'feq' else (an or bn)
        result = 0 if an or bn else int({'feq': rank(a) == rank(b),
            'flt': rank(a) < rank(b), 'fle': rank(a) <= rank(b)}[name])
    else:
        invalid = ass or bs
        if an and bn:
            result = 0x7fc00000 if width == 32 else 0x7ff8000000000000
        elif an or bn:
            result = b if an else a
        elif a & magnitude_mask == 0 and b & magnitude_mask == 0:
            result = (a | b) if name == 'fmin' else (a & b)
        else:
            result = a if (rank(a) <= rank(b) if name == 'fmin' else rank(a) >= rank(b)) else b
        if width == 32:
            result |= BOX
    return result, case['fflags'] | (16 if invalid else 0)


def cases():
    result = []
    for width, normal, nans in (
        (32, [0xff800000, 0xbf800000, 0x80000001, 0x80000000, 0, 1, 0x3f800000, 0x7f800000],
         [0x7fc01234, 0xffc01234, 0x7f800123, 0xff800123]),
        (64, [0xfff0000000000000, 0xbff0000000000000, 0x8000000000000001,
              0x8000000000000000, 0, 1, 0x3ff0000000000000, 0x7ff0000000000000],
         [0x7ff8000000001234, 0xfff8000000001234, 0x7ff0000000000123, 0xfff0000000000123])):
        box = BOX if width == 32 else 0
        normal, nans = ([value | box for value in values] for values in (normal, nans))
        pairs = [(value, value) for value in normal]
        pairs += [(normal[i], normal[7 - i]) for i in range(8)]
        for value in nans:
            pairs += [(value, normal[6]), (normal[6], value), (value, normal[4]),
                      (normal[4], value), (value, value)]
        pairs += [(nans[0], nans[2]), (nans[2], nans[0])]
        if width == 32:
            pairs += [(0x000000003f800000, normal[6]), (normal[6], 0x000000003f800000),
                      (0x12345678ff800123, normal[4]), (normal[4], 0x12345678ff800123),
                      (0x000000003f800000, 0x12345678ff800123)]
        for a, b in pairs:
            for name, code, fp in [('feq', 0xa0102553, False), ('flt', 0xa0101553, False),
                                   ('fle', 0xa0100553, False), ('fmin', 0x28100153, True),
                                   ('fmax', 0x28101153, True)]:
                for flags in (0, 5, 31):
                    result.append(dict(width=width, name=name, a=a, b=b, fflags=flags,
                        word=code | (width == 64) << 25, fp=fp))
    return result


def fixture():
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6000', 'csrs mstatus,t0']
    for index, case in enumerate(cases(), 1):
        value, flags = expected(case)
        lines += [f'li s0,{index}', f'li t0,{case["a"]:#x}', f'li t1,{case["b"]:#x}',
            'fmv.d.x ft0,t0', 'fmv.d.x ft1,t1', f'csrwi fflags,{case["fflags"]}',
            f'probe_{index}: .word {case["word"]:#x} # {case["name"]} width={case["width"]}']
        if case['fp']:
            lines.append('fmv.x.d a0,ft2')
        lines += [f'li t2,{value:#x}', 'bne a0,t2,fail', f'flags_{index}: csrr a1,fflags',
                  f'li t2,{flags}', 'bne a1,t2,fail']
    lines += ['li t1,1', 'j finish', 'fail:', 'slli t1,s0,1', 'ori t1,t1,1',
        'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt: j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def labels():
    text = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(FOLDER / 'test.elf')], text=True)
    return {parts[2]: int(parts[0], 16) for line in text.splitlines() if len(parts := line.split()) == 3}


def inspect(rows):
    symbols, plan = labels(), cases()
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
            assert fp[0] == case['a'] and fp[1] == case['b']
            seen.add(pc)
            assert row['rd_write'] == '1' and int(row['rd_fp']) == case['fp']
            assert int(row['rd']) == (2 if case['fp'] else 10)
            assert int(row['wdata'], 16) == expected(case)[0], (case, row)
            name = f'{case["name"]}_{case["width"]}'
            counts[name] = counts.get(name, 0) + 1
        if pc in flags:
            assert pc not in flag_reads and int(row['instruction'], 16) == 0x001025f3
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '11'
            assert int(row['wdata'], 16) == flags[pc], row
            flag_reads.add(pc)
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '1':
            fp[int(row['rd'])] = int(row['wdata'], 16)
    assert len(seen) == len(flag_reads) == len(plan)
    return dict(probes=len(plan), forms=counts, checked_fflags_reads=len(flag_reads),
        malformed_boxing_probes=sum(case['width'] == 32 and
            (case['a'] >> 32 != 0xffffffff or case['b'] >> 32 != 0xffffffff) for case in plan))


def verify_traces(sail_trace, rtl_trace):
    actual = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), actual)
    assert mismatch is None, mismatch
    result, symbols, controls = inspect(actual), labels(), []
    for width in (32, 64):
        for name in ('feq', 'flt', 'fle', 'fmin', 'fmax'):
            for kind in ('result', 'spurious_NV', 'lost_NV'):
                index = next(i for i, case in enumerate(cases(), 1) if case['width'] == width
                    and case['name'] == name and (kind == 'result' or
                    case['fflags'] == 0 and expected(case)[1] == (16 if kind == 'lost_NV' else 0)))
                broken = copy.deepcopy(actual)
                pc = symbols[f'{"probe" if kind == "result" else "flags"}_{index}']
                row = next(row for row in broken if int(row['pc'], 16) == pc)
                row['wdata'] = f"{int(row['wdata'], 16) ^ (1 if kind == 'result' else 16):016x}"
                try:
                    inspect(broken)
                except AssertionError:
                    controls.append(dict(width=width, name=name, kind=kind))
                else:
                    raise AssertionError(f'Accepted incorrect {width} {name} {kind}')
    return dict(**result, matched_events=events, rejected_mutations=controls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    source = FOLDER / 'test.S'
    dependencies = ['scripts/run_fp_bit_contract.py', 'scripts/audit_rv64i_compute_control.py',
                    'scripts/audit_rv64m_contract.py']
    if args.check:
        report = json.loads((FOLDER / 'report.json').read_bytes())
        assert report['passed'] and report['generator_sha256'] == sha(__file__)
        assert source.read_text(encoding='utf-8') == fixture()
        assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(report['model']['params'])
        assert source_inputs(report['model']['inputs']) == report['model']['inputs']
        assert source_inputs(report['runtime_inputs']) == report['runtime_inputs']
        assert sha(ROOT / report['model']['binary']) == report['model']['binary_sha256']
        for name, key in [('test.S', 'source_sha256'), ('test.elf', 'elf_sha256'),
                          ('commit.csv', 'trace_sha256'), ('sail.csv', 'sail_trace_sha256')]:
            assert sha(FOLDER / name) == report[key]
        for key in ('compile', 'run', 'sail'):
            step = report[key]
            assert step['passed'] and step['exit_code'] == 0 and sha(ROOT / step['log']) == step['log_sha256']
        outcomes = verify_traces(FOLDER / 'sail.csv', FOLDER / 'commit.csv')
        assert outcomes == report['outcomes']
    else:
        source.write_text(fixture(), encoding='utf-8')
        outcomes = run_fixture(source, FOLDER, __file__, verify_traces,
            source_dependencies=dependencies, timeout_cycles=1000000)
        report = json.loads((FOLDER / 'report.json').read_bytes())
        report['complete_profile_validation'] = False
        report['scope'] = 'Finite F/D compare/min/max values and NV accrual; arithmetic rounding, FS permissions and pipeline races separate'
        dump(FOLDER / 'report.json', report)
    print('PASS native F/D compare contract', outcomes, flush=True)


if __name__ == '__main__':
    main()

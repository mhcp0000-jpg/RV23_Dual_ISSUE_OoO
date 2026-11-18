"""Native H/V and identical Sail ELF: F/D classification, signs and raw moves."""
import argparse
import copy
import json
import subprocess

from audit_rv64i_compute_control import sx
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/fp_bit_contract'
BOX = 0xffffffff00000000
MASK = (1 << 64) - 1


def unbox(value, width):
    return 0x7fc00000 if width == 32 and value >> 32 != 0xffffffff else value & ((1 << width) - 1)


def expected(case):
    name, width, a, b = (case[key] for key in ('name', 'width', 'a', 'b'))
    if name.startswith('fmv_to_fp'):
        return (a & 0xffffffff) | BOX if width == 32 else a
    if name.startswith('fmv_to_int'):
        return sx(a, 32) & MASK if width == 32 else a
    x, y = unbox(a, width), unbox(b, width)
    sign = x >> (width - 1)
    if name.startswith('fclass'):
        fraction_bits, exponent_bits = (23, 8) if width == 32 else (52, 11)
        fraction = x & ((1 << fraction_bits) - 1)
        exponent = (x >> fraction_bits) & ((1 << exponent_bits) - 1)
        if exponent == (1 << exponent_bits) - 1:
            category = (9 if fraction & (1 << (fraction_bits - 1)) else 8) if fraction else (0 if sign else 7)
        elif exponent == 0:
            category = (2 if sign else 5) if fraction else (3 if sign else 4)
        else:
            category = 1 if sign else 6
        return 1 << category
    other_sign = y >> (width - 1)
    result_sign = other_sign if name.startswith('fsgnj_') else 1 - other_sign if name.startswith('fsgnjn_') else sign ^ other_sign
    result = (x & ((1 << (width - 1)) - 1)) | result_sign << (width - 1)
    return result | (BOX if width == 32 else 0)


def cases():
    result = []
    for width, values in ((32, [0xff800000, 0xbf800000, 0x807fffff, 0x80000000, 0,
                               0x007fffff, 0x3f800000, 0x7f800000, 0x7f800123, 0xffc12345]),
                          (64, [0xfff0000000000000, 0xbff0000000000000, 0x800fffffffffffff,
                               0x8000000000000000, 0, 0x000fffffffffffff, 0x3ff0000000000000,
                               0x7ff0000000000000, 0x7ff0000000000123, 0xfff8000000001234])):
        suffix = 's' if width == 32 else 'd'
        raw = [value | (BOX if width == 32 else 0) for value in values]
        if width == 32:
            raw += [0x000000003f800000, 0x12345678ff800123, 0x00000000ffc12345]
        for a in raw:
            result.append(dict(name=f'fclass_{suffix}', width=width, a=a, b=0,
                instruction=f'fclass.{suffix} a0,ft0', word=0xe0001553 | (width == 64) << 25, fp=False))
        for op, f3 in (('fsgnj', 0), ('fsgnjn', 1), ('fsgnjx', 2)):
            signs = [raw[0], raw[4], raw[8], raw[9]] + (raw[-1:] if width == 32 else [])
            for a in raw:
                for b in signs:
                    result.append(dict(name=f'{op}_{suffix}', width=width, a=a, b=b,
                        instruction=f'{op}.{suffix} ft2,ft0,ft1',
                        word=0x20100153 | (width == 64) << 25 | f3 << 12, fp=True))
        for a in [0, MASK, 0x80000000, 0x1234567889abcdef, 0x7f800123,
                  0x00000000ffc12345, 0x7ff0000000000123, 0x8000000000000000]:
            result.append(dict(name=f'fmv_to_fp_{suffix}', width=width, a=a, b=0,
                instruction='fmv.w.x ft2,t0' if width == 32 else 'fmv.d.x ft2,t0',
                word=0xf0028153 | (width == 64) << 25, fp=True))
            result.append(dict(name=f'fmv_to_int_{suffix}', width=width, a=a, b=0,
                instruction='fmv.x.w a0,ft0' if width == 32 else 'fmv.x.d a0,ft0',
                word=0xe0000553 | (width == 64) << 25, fp=False))
    return [dict(case, fflags=flags) for case in result for flags in (0, 5, 31)]


def fixture():
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6000', 'csrs mstatus,t0']
    for index, case in enumerate(cases(), 1):
        lines += [f'li s0,{index}', f'li t0,{case["a"]:#x}', f'li t1,{case["b"]:#x}',
            'fmv.d.x ft0,t0', 'fmv.d.x ft1,t1', f'csrwi fflags,{case["fflags"]}',
            f'probe_{index}: {case["instruction"]}']
        if case['fp']:
            lines += ['fmv.x.d a0,ft2']
        lines += [f'li t2,{expected(case):#x}', 'bne a0,t2,fail',
            f'flags_{index}: csrr a1,fflags', f'li t2,{case["fflags"]}', 'bne a1,t2,fail']
    lines += ['li t1,1', 'j finish', 'fail:', 'slli t1,s0,1', 'ori t1,t1,1',
        'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt: j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def labels():
    text = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(FOLDER / 'test.elf')], text=True)
    return {name: int(address, 16) for line in text.splitlines()
            if len(parts := line.split()) == 3 for address, _, name in [parts]}


def inspect(rows):
    symbols, plan = labels(), cases()
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    flags = {symbols[f'flags_{i}']: case['fflags'] for i, case in enumerate(plan, 1)}
    counts, categories, seen, flag_reads = {}, {32: set(), 64: set()}, set(), set()
    registers, fp = [None] * 32, [None] * 32
    registers[0] = 0
    for row in rows:
        pc = int(row['pc'], 16)
        if pc >= 0x80000000:
            assert row['trap'] == '0', row
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and int(row['instruction'], 16) == case['word'], row
            seen.add(pc)
            a = registers[5] if case['name'].startswith('fmv_to_fp') else fp[0]
            assert a == case['a']
            if case['name'].startswith('fsgnj'):
                assert fp[1] == case['b']
            assert row['rd_write'] == '1' and int(row['rd_fp']) == case['fp']
            assert int(row['rd']) == (2 if case['fp'] else 10)
            assert int(row['wdata'], 16) == expected(case), (case, row)
            counts[case['name']] = counts.get(case['name'], 0) + 1
            if case['name'].startswith('fclass'):
                categories[case['width']].add(expected(case))
        if pc in flags:
            assert pc not in flag_reads and row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '11'
            assert int(row['instruction'], 16) == 0x001025f3
            assert int(row['wdata'], 16) == flags[pc]
            flag_reads.add(pc)
        if row['trap'] == '0' and row['rd_write'] == '1':
            rd, value = int(row['rd']), int(row['wdata'], 16)
            if row['rd_fp'] == '1':
                fp[rd] = value
            elif rd:
                registers[rd] = value
    assert len(seen) == len(plan) == len(flag_reads)
    assert all(value == {1 << i for i in range(10)} for value in categories.values())
    return dict(probes=len(plan), forms=counts, all_ten_classes_per_format=True,
                preserved_fflags_reads=len(flag_reads), initial_fflags_values=[0, 5, 31])


def verify_traces(sail_trace, rtl_trace):
    actual = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), actual)
    assert mismatch is None, mismatch
    result = inspect(actual)
    symbols = labels()
    controls = []
    for name in result['forms']:
        index = next(i for i, case in enumerate(cases(), 1) if case['name'] == name)
        broken = copy.deepcopy(actual)
        row = next(row for row in broken if int(row['pc'], 16) == symbols[f'probe_{index}'])
        row['wdata'] = f"{int(row['wdata'], 16) ^ 1:016x}"
        try:
            inspect(broken)
        except AssertionError:
            controls.append(name)
        else:
            raise AssertionError(f'Incorrect {name} accepted')
    flag_controls = []
    for flags, wrong in ((31, 0), (0, 16)):
        broken = copy.deepcopy(actual)
        index = next(i for i, case in enumerate(cases(), 1) if case['fflags'] == flags)
        row = next(row for row in broken if int(row['pc'], 16) == symbols[f'flags_{index}'])
        row['wdata'] = f'{wrong:016x}'
        try:
            inspect(broken)
        except AssertionError:
            flag_controls.append(dict(original=flags, wrong=wrong))
        else:
            raise AssertionError(f'Changed fflags {flags}->{wrong} accepted')
    result['rejected_fflags_mutations'] = flag_controls
    return dict(**result, matched_events=events, rejected_result_mutations=controls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    source = FOLDER / 'test.S'
    dependencies = ['scripts/audit_rv64i_compute_control.py', 'scripts/audit_rv64m_contract.py']
    if args.check:
        report = json.loads((FOLDER / 'report.json').read_bytes())
        assert report['passed'] and report['generator_sha256'] == sha(__file__)
        assert source.read_text(encoding='utf-8') == fixture()
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
        report['scope'] = 'Finite F/D bit semantics and sticky flags; arithmetic, rounding, FS permissions and pipeline races separate'
        dump(FOLDER / 'report.json', report)
    print('PASS native F/D bit contract', outcomes, flush=True)


if __name__ == '__main__':
    main()

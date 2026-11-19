"""Native FENCE.I ignored fields with patched 16/32-bit instruction execution."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs

FOLDER = ROOT / 'out/rva23/fencei_selfmod_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py']


def cases():
    fields = {(imm, rd, rs1) for imm in {0, 4095, *[1 << bit for bit in range(12)]}
        for rd, rs1 in ((0, 0), (1, 31), (31, 1))}
    fields |= {(0, reg, (reg * 7 + 3) % 32) for reg in range(32)}
    assert len(fields) == 74
    plan = []
    for width in (16, 32):
        for index, (imm, rd, rs1) in enumerate(sorted(fields)):
            plan.append(dict(width=width, offset=(index % (64 // (width // 8))) * (width // 8),
                word=imm << 20 | rs1 << 15 | 1 << 12 | rd << 7 | 0x0f,
                old=0x4505 if width == 16 else 0x00100513,
                new=0x4509 if width == 16 else 0x00200513))
    assert len(plan) == 148
    return plan


def fixture(plan):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0']
    for index, case in enumerate(plan, 1):
        store = 'sh' if case['width'] == 16 else 'sw'
        lines += [f'la s0,patch_{index}', f'li s1,{case["old"]:#x}', f'{store} s1,0(s0)',
            'fence.i', 'jalr ra,s0,0', 'li t0,1', 'bne a0,t0,fail',
            f'li s1,{case["new"]:#x}', f'write_{index}:{store} s1,0(s0)',
            f'probe_{index}:.word {case["word"]:#x}', 'jalr ra,s0,0', 'li t0,2', 'bne a0,t0,fail']
    lines += ['li t1,1', 'j finish', 'fail:li t1,3', 'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt']
    for index, case in enumerate(plan, 1):
        lines += ['.balign 64,0']
        if case['offset']:
            lines.append(f'.space {case["offset"]},0')
        lines += [f'patch_{index}:', f'.hword {case["old"]:#x}', '.hword 0x8082'] if case['width'] == 16 else [
            f'patch_{index}:', f'.word {case["old"]:#x}', '.word 0x00008067']
    lines += ['.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost', 'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, symbols):
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    patches = {symbols[f'patch_{i}']: case for i, case in enumerate(plan, 1)}
    writes = {symbols[f'write_{i}']: (symbols[f'patch_{i}'], case) for i, case in enumerate(plan, 1)}
    registers, seen, modified, executions = [None] * 32, set(), set(), {pc: [] for pc in patches}
    registers[0] = 0
    for index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        assert pc < 0x80000000 or row['trap'] == '0', row
        if pc in writes:
            address, case = writes[pc]
            assert pc not in modified and word == 9 << 20 | 8 << 15 | (1 if case['width'] == 16 else 2) << 12 | 0x23
            assert registers[8] == address and registers[9] == case['new'] and row['rd_write'] == '0'
            modified.add(pc)
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and word == case['word'] and row['rd_write'] == '0'
            assert symbols[f'write_{next(i for i, c in enumerate(plan, 1) if c is case)}'] in modified
            assert int(rows[index + 1]['pc'], 16) == pc + 4
            seen.add(pc)
        if pc in patches:
            case, values = patches[pc], executions[pc]
            assert pc % 64 == case['offset'] and len(values) < 2
            assert word == case['old' if not values else 'new']
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '10'
            assert int(row['wdata'], 16) == len(values) + 1
            assert int(rows[index + 1]['pc'], 16) == pc + case['width'] // 8
            values.append(word)
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    assert seen == set(probes) and modified == set(writes) and all(len(values) == 2 for values in executions.values())
    return dict(probes=len(plan), patched_executions=2 * len(plan), field_encodings=len({case['word'] for case in plan}),
        halfword_line_positions=sorted({case['offset'] for case in plan if case['width'] == 16}),
        word_line_positions=sorted({case['offset'] for case in plan if case['width'] == 32}))


def verifier(plan, folder):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        result, controls = inspect(rows, plan, symbols), []
        for width in (16, 32):
            i = next(i for i, case in enumerate(plan, 1) if case['width'] == width)
            for kind in ('stale_instruction', 'ignored_rd_write'):
                broken = copy.deepcopy(rows)
                if kind == 'stale_instruction':
                    row = [row for row in broken if int(row['pc'], 16) == symbols[f'patch_{i}']][1]
                    row['instruction'] = f'{plan[i - 1]["old"]:08x}'
                else:
                    row = next(row for row in broken if int(row['pc'], 16) == symbols[f'probe_{i}'])
                    row['rd_write'] = '1'
                try:
                    inspect(broken, plan, symbols)
                except AssertionError:
                    controls.append(f'{width}:{kind}')
                else:
                    raise AssertionError('Incorrect FENCE.I execution accepted')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    plan = cases()
    source, verify = FOLDER / 'test.S', verifier(plan, FOLDER)
    if args.check:
        result = check_fixture(FOLDER, __file__, fixture(plan), verify)
    else:
        source.write_text(fixture(plan), encoding='utf-8')
        result = run_fixture(source, FOLDER, __file__, verify, source_dependencies=DEPENDENCIES, timeout_cycles=4000000)
    print('PASS FENCE.I ignored fields and self-modifying code', result, flush=True)


if __name__ == '__main__':
    main()

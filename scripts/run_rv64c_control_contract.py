"""Native RV64C control boundaries, halfword PCs and indirect source/link alias."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from audit_rv64c_contract import decode
from audit_rv64m_contract import MASK
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/rv64c_control_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/audit_rv64c_contract.py',
    'scripts/audit_rv64i_compute_control.py', 'scripts/audit_rv64i_memory_values.py',
    'scripts/audit_rv64m_contract.py']
CJ_OFFSETS = [-2048, -2046, -1024, -512, -256, -128, -64, -32, -16, -8,
              -6, -4, -2, 2, 4, 6, 8, 16, 32, 64, 128, 256, 512, 1024, 2046]
CB_OFFSETS = [-256, -254, -128, -64, -32, -16, -8, -6, -4, -2,
              0, 2, 4, 6, 8, 16, 32, 64, 128, 254]
BATCH = 200


def cases():
    plan = []
    for offset in CJ_OFFSETS:
        for phase in (0, 2):
            plan.append(dict(name='j', offset=offset, phase=phase, rs1=None))
    for name in ('beqz', 'bnez'):
        for offset in CB_OFFSETS:
            for rs1 in range(8, 16):
                for value in (0, 1, MASK, 1 << 63):
                    taken = (value == 0) if name == 'beqz' else (value != 0)
                    if offset == 0 and taken:
                        continue  # A taken self-loop needs interrupt-driven exit.
                    for phase in (0, 2):
                        plan.append(dict(name=name, offset=offset, phase=phase,
                            rs1=rs1, value=value, taken=taken))
    for name in ('jr', 'jalr'):
        for rs1 in range(1, 32):
            for odd in (0, 1):
                for phase in (0, 2):
                    for target_phase in (0, 2):
                        plan.append(dict(name=name, rs1=rs1, odd=odd, phase=phase,
                            offset=4 + ((target_phase - phase) % 4), target_phase=target_phase))
    return plan


def word(case):
    name, offset, rs1 = (case[key] for key in ('name', 'offset', 'rs1'))
    if name in ('jr', 'jalr'):
        return (0x8002 if name == 'jr' else 0x9002) | rs1 << 7
    if name == 'j':
        return (0xa001 | ((offset >> 11) & 1) << 12 | ((offset >> 10) & 1) << 8
            | ((offset >> 8) & 3) << 9 | ((offset >> 7) & 1) << 6
            | ((offset >> 6) & 1) << 7 | ((offset >> 5) & 1) << 2
            | ((offset >> 4) & 1) << 11 | ((offset >> 1) & 7) << 3)
    return ((0xc001 if name == 'beqz' else 0xe001) | (rs1 - 8) << 7
        | ((offset >> 8) & 1) << 12 | ((offset >> 6) & 3) << 5
        | ((offset >> 5) & 1) << 2 | ((offset >> 3) & 3) << 10
        | ((offset >> 1) & 3) << 3)


def fixture(plan):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0']
    for index, case in enumerate(plan, 1):
        name, rs1, offset = (case[key] for key in ('name', 'rs1', 'offset'))
        ret = 6 if rs1 == 5 else 5
        target, probe, cont = (f'{label}_{index}' for label in ('target', 'probe', 'continue'))
        lines += [f'la x{ret},{cont}']
        if rs1 != 1:
            lines.append('li ra,0x123456789abcdef0')
        if name in ('jr', 'jalr'):
            lines += [f'la x{rs1},{target}', f'ori x{rs1},x{rs1},{case["odd"]}']
        elif rs1 is not None:
            lines.append(f'li x{rs1},{case["value"]:#x}')
        lines += [f'j {probe}', '.balign 4']
        start_phase = (case['phase'] - offset) % 4 if offset < 0 else case['phase']
        if start_phase:
            lines.append('.hword 1')
        trampoline = f'.hword {0x8002 | ret << 7:#x} # c.jr x{ret}'
        if offset < 0:
            lines += [f'{target}: {trampoline}', f'.fill {(-offset - 2) // 2},2,1',
                f'{probe}: .hword {word(case):#x} # c.{name}', trampoline]
        elif offset == 0:
            lines += [f'{target}:', f'{probe}: .hword {word(case):#x} # c.{name}', trampoline]
        else:
            lines.append(f'{probe}: .hword {word(case):#x} # c.{name}')
            if offset > 2:
                lines += [trampoline, f'.fill {(offset - 4) // 2},2,1']
            lines.append(f'{target}: {trampoline}')
        lines.append(f'{cont}:')
        if name == 'jalr':
            lines += [f'la x{ret},{probe}', f'addi x{ret},x{ret},2', f'bne ra,x{ret},fail']
    lines += ['li t1,1', 'j finish', '.balign 4', 'fail: li t1,3', 'finish:',
        'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt', '.section .tohost,"aw"',
        '.balign 8', '.globl tohost,fromhost', 'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, symbols):
    probes = {symbols[f'probe_{i}']: (i, case) for i, case in enumerate(plan, 1)}
    registers, seen, counts = [None] * 32, set(), {}
    registers[0] = 0
    odd_inputs, alias_sources, halfword_targets = 0, 0, 0
    for row_index, row in enumerate(rows):
        pc = int(row['pc'], 16)
        if pc >= 0x80000000:
            assert row['trap'] == '0', row
        if pc in probes:
            index, case = probes[pc]
            name, rs1 = case['name'], case['rs1']
            target = symbols[f'target_{index}']
            assert pc not in seen and pc % 4 == case['phase']
            assert target - pc == case['offset'] and int(row['instruction'], 16) == word(case)
            ret = 6 if rs1 == 5 else 5
            assert registers[ret] == symbols[f'continue_{index}']
            taken = case.get('taken', True)
            expected_pc = target if taken else pc + 2
            if name in ('jr', 'jalr'):
                assert registers[rs1] == target | case['odd']
                assert target % 4 == case['target_phase']
                odd_inputs += case['odd']
                alias_sources += int(name == 'jalr' and rs1 == 1)
            elif rs1 is not None:
                assert registers[rs1] == case['value']
            value, rd = ((pc + 2, 1) if name == 'jalr' else (None, 0))
            item = decode(word(case), pc, registers)
            assert item[:4] == (name, rd, value, expected_pc), (case, item, hex(expected_pc))
            if name == 'jalr':
                assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '1'
                assert int(row['wdata'], 16) == pc + 2, row
            else:
                assert row['rd_write'] == '0' or (row['rd_fp'] == '0' and row['rd'] == '0'), row
            assert int(rows[row_index + 1]['pc'], 16) == expected_pc, (case, row, hex(expected_pc))
            halfword_targets += int(expected_pc % 4 == 2)
            stats = counts.setdefault(name, dict(probes=0, taken=0, not_taken=0))
            stats['probes'] += 1
            stats['taken' if taken else 'not_taken'] += 1
            seen.add(pc)
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    assert len(seen) == len(plan)
    return dict(probes=len(plan), forms=counts, odd_indirect_inputs=odd_inputs,
        jalr_x1_source_alias=alias_sources, next_pc_halfword_phase=halfword_targets)


def verifier(plan, folder):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        result, controls = inspect(rows, plan, symbols), []
        for name in result['forms']:
            probe_index = next(i for i, case in enumerate(plan, 1) if case['name'] == name)
            index = next(i for i, row in enumerate(rows) if int(row['pc'], 16) == symbols[f'probe_{probe_index}'])
            for kind in (('next_pc', 'link') if name == 'jalr' else ('next_pc',)):
                broken = copy.deepcopy(rows)
                row, key = (broken[index], 'wdata') if kind == 'link' else (broken[index + 1], 'pc')
                row[key] = f"{int(row[key], 16) ^ 2:016x}"
                try:
                    inspect(broken, plan, symbols)
                except AssertionError:
                    controls.append(dict(name=name, kind=kind))
                else:
                    raise AssertionError(f'Incorrect C.{name} {kind} accepted')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    plan = cases()
    FOLDER.mkdir(parents=True, exist_ok=True)
    batches = [plan[start:start + BATCH] for start in range(0, len(plan), BATCH)]
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='Finite RV64C control signed-boundary/bit offsets, all branch compact registers, all indirect nonzero source registers, both instruction/target halfword phases, odd indirect pointers and JALR x1 alias. Taken zero-offset loops, every immediate, faults, interrupts and all schedules separate',
        inputs=source_inputs(DEPENDENCIES), probes=len(plan), cases=[])
    if args.check:
        saved = json.loads((FOLDER / 'report.json').read_bytes())
        assert saved['passed'] and saved['generator_sha256'] == top['generator_sha256']
        assert saved['inputs'] == top['inputs'] and saved['probes'] == len(plan) and len(saved['cases']) == len(batches)
    else:
        dump(FOLDER / 'report.json', top)
    for index, batch in enumerate(batches):
        folder = FOLDER / str(index)
        folder.mkdir(exist_ok=True)
        source, verify = folder / 'test.S', verifier(batch, folder)
        if args.check:
            outcome = check_fixture(folder, __file__, fixture(batch), verify)
            old = saved['cases'][index]
            assert old['index'] == index and old['report_sha256'] == sha(folder / 'report.json') and old['outcomes'] == outcome
        else:
            source.write_text(fixture(batch), encoding='utf-8')
            outcome = run_fixture(source, folder, __file__, verify,
                source_dependencies=DEPENDENCIES, timeout_cycles=2000000)
        top['cases'].append(dict(index=index, report_sha256=sha(folder / 'report.json'), outcomes=outcome))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS native RV64C control', index, outcome['probes'], 'probes;',
            outcome['matched_events'], 'Sail/RTL events;', len(outcome['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

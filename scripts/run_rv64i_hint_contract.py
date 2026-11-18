"""Finite RV64I HINT families using immutable C-suite snapshot scaffolding."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from run_hv_sail_fixture import run_fixture
from run_rvc_hint_contract import (DEPENDENCIES as C_DEPENDENCIES, FCSR, GUARD,
    fixture as c_fixture, gpr, fpr)
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/rv64i_hint_contract'
DEPENDENCIES = [*C_DEPENDENCIES, 'scripts/run_rvc_hint_contract.py']
BATCH = 128


def cases():
    plan = []
    def add(name, word):
        plan.append(dict(name=name, word=word))
    for name, opcode in [('lui', 0x37), ('auipc', 0x17)]:
        for immediate in sorted({0, 0xfffff, 0x7ffff, *[1 << bit for bit in range(20)]}):
            add(name, immediate << 12 | opcode)
    for name, f3 in [('addi', 0), ('slti', 2), ('sltiu', 3), ('xori', 4), ('ori', 6), ('andi', 7), ('addiw', 0)]:
        for rs1 in (0, 1, 8, 15, 31):
            for imm in (-2048, -1, 0, 1, 2047):
                add('nop' if name == 'addi' and rs1 == imm == 0 else name,
                    (imm & 4095) << 20 | rs1 << 15 | f3 << 12 | (0x1b if name == 'addiw' else 0x13))
    for name, opcode, f3, f7 in [
        ('add', 0x33, 0, 0), ('sub', 0x33, 0, 32), ('sll', 0x33, 1, 0),
        ('slt', 0x33, 2, 0), ('sltu', 0x33, 3, 0), ('xor', 0x33, 4, 0),
        ('srl', 0x33, 5, 0), ('sra', 0x33, 5, 32), ('or', 0x33, 6, 0), ('and', 0x33, 7, 0),
        ('addw', 0x3b, 0, 0), ('subw', 0x3b, 0, 32), ('sllw', 0x3b, 1, 0),
        ('srlw', 0x3b, 5, 0), ('sraw', 0x3b, 5, 32)]:
        pairs = {(rs1, (rs1 * 7 + 3) % 32) for rs1 in range(32)} | {(0, 0), (1, 1), (31, 31)}
        if name == 'add':
            pairs |= {(0, rs2) for rs2 in range(2, 6)}
        for rs1, rs2 in sorted(pairs):
            add('ntl' if name == 'add' and rs1 == 0 and 2 <= rs2 <= 5 else name,
                f7 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | opcode)
    for name, opcode, f3, upper, count in [
        ('slli', 0x13, 1, 0, 64), ('srli', 0x13, 5, 0, 64), ('srai', 0x13, 5, 0x400, 64),
        ('slliw', 0x1b, 1, 0, 32), ('srliw', 0x1b, 5, 0, 32), ('sraiw', 0x1b, 5, 0x400, 32)]:
        for shift in range(count):
            add(name, (upper | shift) << 20 | ((shift * 7) % 32) << 15 | f3 << 12 | opcode)
    add('semihost_entry_marker', 0x01f01013)
    add('semihost_exit_marker', 0x40705013)
    for pred, succ in [(0, succ) for succ in range(16)] + [(pred, 0) for pred in range(1, 16)]:
        for rd, rs1 in ((0, 0), (0, 31), (31, 0)):
            add('pause' if pred == 1 and succ == rd == rs1 == 0 else 'fence_hint',
                pred << 24 | succ << 20 | rs1 << 15 | rd << 7 | 0x0f)
    assert len(plan) == len({case['word'] for case in plan})
    assert all(case['word'] & 3 == 3 for case in plan)
    return plan


def fixture(plan, batch_index):
    # Reuse the unchanged register snapshot/zero-trap scaffold. Only labeled
    # probe directives widen; the permanent-zero probe remains 16-bit.
    text = c_fixture(plan, batch_index)
    assert text.count(': .hword ') == len(plan)
    return text.replace(': .hword ', ': .word ')


def inspect(rows, plan, batch_index, symbols):
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    snapshots, stores, guards, fcsrs = {}, {}, set(), set()
    for index in range(1, len(plan) + 1):
        pc = symbols[f'probe_{index}']
        for floating in (False, True):
            for reg in range(32):
                offset = (256 if floating else 0) + reg * 8
                snapshots[symbols[f'snapshot_{index}_{int(floating)}_{reg}']] = (
                    offset << 20 | 8 << 15 | 3 << 12 | 6 << 7 | 3,
                    fpr(reg) if floating else gpr(reg))
                store_word = ((offset >> 5) << 25 | reg << 20 | 8 << 15 | 3 << 12
                    | (offset & 31) << 7 | (0x27 if floating else 0x23))
                stores[pc + 4 + (32 * int(floating) + reg) * 4] = store_word
        guards.update(symbols[f'guard_{index}_{guard}'] for guard in range(2))
        fcsrs.add(symbols[f'fcsr_{index}'])
    registers, fp = [None] * 32, [None] * 32
    registers[0] = 0
    seen, seen_loads, seen_stores, seen_guards, seen_fcsr, traps, counts = set(), set(), set(), set(), set(), [], {}
    for index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if pc >= 0x80000000 and row['trap'] == '1':
            assert pc == symbols['zero_probe'] and word == 0
            assert int(row['cause']) == 2 and int(row['tval'], 16) == 0 and row['rd_write'] == '0'
            assert int(rows[index + 1]['pc'], 16) == symbols['trap_handler']
            traps.append(pc)
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and word == case['word'] and row['trap'] == '0'
            assert registers == [gpr(reg) for reg in range(32)] and fp == [fpr(reg) for reg in range(32)]
            if row['rd_write'] == '1':
                rd = int(row['rd'])
                assert row['rd_fp'] == '0'
                if rd:
                    assert int(row['wdata'], 16) == registers[rd]
            assert int(rows[index + 1]['pc'], 16) == pc + 4
            seen.add(pc)
            counts[case['name']] = counts.get(case['name'], 0) + 1
        if pc in stores:
            assert pc not in seen_stores and word == stores[pc] and row['rd_write'] == '0'
            seen_stores.add(pc)
        if pc in snapshots:
            instruction, value = snapshots[pc]
            assert pc not in seen_loads and word == instruction
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '6'
            assert int(row['wdata'], 16) == value, row
            seen_loads.add(pc)
        if pc in guards:
            assert pc not in seen_guards and word & 127 == 3
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '6'
            assert int(row['wdata'], 16) == GUARD
            seen_guards.add(pc)
        if pc in fcsrs:
            assert pc not in seen_fcsr and word == 0x00302373
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '6'
            assert int(row['wdata'], 16) == FCSR
            seen_fcsr.add(pc)
        if row['trap'] == '0' and row['rd_write'] == '1':
            rd, value = int(row['rd']), int(row['wdata'], 16)
            if row['rd_fp'] == '1':
                fp[rd] = value
            elif rd:
                registers[rd] = value
    assert len(seen) == len(seen_fcsr) == len(plan)
    assert seen_stores == set(stores) and seen_loads == set(snapshots) and seen_guards == guards
    assert traps == [symbols['zero_probe']] and symbols['zero_probe'] % 4 == 2 * (batch_index % 2)
    return dict(probes=len(plan), families=counts, register_snapshot_values=len(snapshots),
        checked_snapshot_stores=len(stores), guard_reads=len(guards), fcsr_reads=len(fcsrs))


def verifier(plan, batch_index, folder):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        result, controls = inspect(rows, plan, batch_index, symbols), []
        for name in result['families']:
            case_index = next(i for i, case in enumerate(plan, 1) if case['name'] == name)
            pc = symbols[f'snapshot_{case_index}_0_1']
            broken = copy.deepcopy(rows)
            row = next(row for row in broken if int(row['pc'], 16) == pc)
            row['wdata'] = f"{int(row['wdata'], 16) ^ 1:016x}"
            try:
                inspect(broken, plan, batch_index, symbols)
            except AssertionError:
                controls.append(name)
            else:
                raise AssertionError(f'Incorrect {name} snapshot accepted')
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
        scope='Finite RV64I HINT family/field samples with inert GPR/FPR/FCSR/snapshot guards; includes custom HINT policy, NTL, PAUSE, semihost marker NOPs and null-set fences. Not exhaustive HINT code points, all CSRs/privileges, semihost service ABI, timing or global ordering proof',
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
        source, verify = folder / 'test.S', verifier(batch, index, folder)
        if args.check:
            outcome = check_fixture(folder, __file__, fixture(batch, index), verify)
            old = saved['cases'][index]
            assert old['index'] == index and old['report_sha256'] == sha(folder / 'report.json') and old['outcomes'] == outcome
        else:
            source.write_text(fixture(batch, index), encoding='utf-8')
            outcome = run_fixture(source, folder, __file__, verify,
                source_dependencies=DEPENDENCIES, timeout_cycles=3000000)
        top['cases'].append(dict(index=index, report_sha256=sha(folder / 'report.json'), outcomes=outcome))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS native RV64I HINT', index, outcome['probes'], 'probes;',
            outcome['matched_events'], 'Sail/RTL events;', len(outcome['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

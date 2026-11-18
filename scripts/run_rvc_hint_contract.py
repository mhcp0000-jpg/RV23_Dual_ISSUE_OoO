"""All RV64 base-C HINT code points, register snapshots and permanent zero trap."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from audit_rv64i_compute_control import sx
from audit_rv64i_memory_values import LOADS, STORES, initial_memory
from audit_rv64m_contract import MASK
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/rvc_hint_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/audit_rv64i_compute_control.py',
    'scripts/audit_rv64i_memory_values.py', 'scripts/audit_rv64m_contract.py']
BASE, FCSR, GUARD, BATCH = 0x80080000, 0x65, 0x5aa5d33d369cc963, 128


def gpr(reg):
    return 0 if reg == 0 else BASE if reg == 8 else (0x8000000000000001 ^ reg * 0x0101010101010101) & MASK


def fpr(reg):
    return [0x7ff0000000000100, 0x7ff8000000000100, 0x100,
            0x8000000000000100, 0x3ff0000000000100, 0xfff0000000000100][reg % 6] | reg


def cases():
    plan = []
    def add(name, word):
        plan.append(dict(name=name, word=word))
    def ci(base, rd, imm):
        return base | rd << 7 | ((imm & 63) >> 5) << 12 | (imm & 31) << 2
    add('nop', 1)
    for imm in range(1, 64):
        add('nop_hint', ci(1, 0, imm))
    for rd in range(1, 32):
        add('addi_zero', ci(1, rd, 0))
    for imm in range(64):
        add('li_x0', ci(0x4001, 0, imm))
    for imm in range(1, 64):
        add('lui_x0', ci(0x6001, 0, imm))
    for rs2 in range(1, 32):
        add('mv_x0', 0x8002 | rs2 << 2)
        add('ntl' if 2 <= rs2 <= 5 else 'add_x0', 0x9002 | rs2 << 2)
    for shift in range(64):
        add('slli_x0', ci(2, 0, shift))
    for rd in range(1, 32):
        add('slli_zero', ci(2, rd, 0))
    for rd in range(8, 16):
        add('srli_zero', 0x8001 | (rd - 8) << 7)
        add('srai_zero', 0x8401 | (rd - 8) << 7)
    assert len(plan) == len({case['word'] for case in plan}) == 395
    return plan


def fixture(plan, batch_index):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,trap_handler', 'csrw mtvec,t0', 'csrw mscratch,zero',
        'li t0,0x6000', 'csrs mstatus,t0', f'li t0,{FCSR}', 'csrw fcsr,t0',
        f'li s0,{BASE:#x}', f'li t0,{GUARD:#x}', 'sd t0,512(s0)', 'sd t0,520(s0)']
    for reg in range(32):
        lines += [f'li t0,{fpr(reg):#x}', f'fmv.d.x f{reg},t0']
    lines += [f'li x{reg},{gpr(reg):#x}' for reg in range(1, 32)]
    for index, case in enumerate(plan, 1):
        lines += [f'li t1,{gpr(6):#x}', f'li t2,{gpr(7):#x}',
            f'probe_{index}: .hword {case["word"]:#x} # {case["name"]}']
        lines += [f'sd x{reg},{reg * 8}(s0)' for reg in range(32)]
        lines += [f'fsd f{reg},{256 + reg * 8}(s0)' for reg in range(32)]
        for floating in (False, True):
            for reg in range(32):
                lines.append(f'snapshot_{index}_{int(floating)}_{reg}: ld t1,{(256 if floating else 0) + reg * 8}(s0)')
        for guard in range(2):
            lines.append(f'guard_{index}_{guard}: ld t1,{512 + guard * 8}(s0)')
        lines += [f'fcsr_{index}: csrr t1,fcsr', f'li t2,{FCSR}', 'bne t1,t2,fail']
    lines.append('.balign 4')
    if batch_index % 2:
        lines.append('.hword 1')
    lines += ['zero_probe:.hword 0', 'after_zero:csrr t1,mscratch', 'li t2,1',
        'bne t1,t2,fail', 'li t1,1', 'j finish', '.balign 4', 'trap_handler:',
        'csrr t0,mcause', 'li t1,2', 'bne t0,t1,fail', 'csrr t0,mtval', 'bnez t0,fail',
        'csrr t0,mepc', 'la t1,zero_probe', 'bne t0,t1,fail', 'addi t0,t0,2',
        'csrw mepc,t0', 'li t0,1', 'csrw mscratch,t0', 'mret',
        'fail:li t1,3', 'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, batch_index, symbols, initial):
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    snapshots, guards, fcsrs = {}, set(), set()
    for index in range(1, len(plan) + 1):
        for floating in (False, True):
            for reg in range(32):
                snapshots[symbols[f'snapshot_{index}_{int(floating)}_{reg}']] = fpr(reg) if floating else gpr(reg)
        guards.update(symbols[f'guard_{index}_{guard}'] for guard in range(2))
        fcsrs.add(symbols[f'fcsr_{index}'])
    registers, fp, memory = [None] * 32, [None] * 32, initial.copy()
    registers[0] = 0
    seen, seen_snapshots, seen_guards, seen_fcsr, traps, counts = set(), set(), set(), set(), [], {}
    def read(address, size):
        assert all(address + i in memory for i in range(size)), (hex(address), size)
        return sum(memory[address + i] << (8 * i) for i in range(size))
    for index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if pc >= 0x80000000 and row['trap'] == '1':
            assert pc == symbols['zero_probe'] and word == 0
            assert int(row['cause']) == 2 and int(row['tval'], 16) == 0 and row['rd_write'] == '0'
            assert int(rows[index + 1]['pc'], 16) == symbols['trap_handler']
            traps.append(pc)
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and row['trap'] == '0' and word == case['word']
            assert registers == [gpr(reg) for reg in range(32)]
            assert fp == [fpr(reg) for reg in range(32)]
            if row['rd_write'] == '1':
                rd = int(row['rd'])
                assert row['rd_fp'] == '0'
                if rd:
                    assert int(row['wdata'], 16) == registers[rd], row
            assert int(rows[index + 1]['pc'], 16) == pc + 2
            seen.add(pc)
            counts[case['name']] = counts.get(case['name'], 0) + 1
        if pc >= 0x80000000 and row['trap'] == '0' and word & 127 in (3, 0x23, 0x27):
            opcode, f3 = word & 127, (word >> 12) & 7
            load = opcode == 3
            base = registers[(word >> 15) & 31]
            assert base is not None
            imm = word >> 20 if load else (word >> 25) << 5 | (word >> 7) & 31
            address = (base + sx(imm, 12)) & MASK
            if load:
                _, size, sign = LOADS[f3]
                value = read(address, size)
                value = (sx(value, size * 8) if sign else value) & MASK
                rd = (word >> 7) & 31
                assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                assert int(row['wdata'], 16) == value, row
            else:
                size = 8 if opcode == 0x27 else STORES[f3][1]
                if opcode == 0x27:
                    assert f3 == 3
                source = (word >> 20) & 31
                value = fp[source] if opcode == 0x27 else registers[source]
                assert value is not None
                for byte in range(size):
                    memory[address + byte] = (value >> (8 * byte)) & 255
        if pc in snapshots:
            assert pc not in seen_snapshots and int(row['wdata'], 16) == snapshots[pc]
            seen_snapshots.add(pc)
        if pc in guards:
            assert pc not in seen_guards and int(row['wdata'], 16) == GUARD
            seen_guards.add(pc)
        if pc in fcsrs:
            assert pc not in seen_fcsr and word == 0x00302373
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '6'
            assert int(row['wdata'], 16) == FCSR
            seen_fcsr.add(pc)
        if pc == symbols['after_zero']:
            assert row['trap'] == '0' and int(row['wdata'], 16) == 1
        if row['trap'] == '0' and row['rd_write'] == '1':
            rd, value = int(row['rd']), int(row['wdata'], 16)
            if row['rd_fp'] == '1':
                fp[rd] = value
            elif rd:
                registers[rd] = value
    assert len(seen) == len(seen_fcsr) == len(plan)
    assert seen_snapshots == set(snapshots) and seen_guards == guards
    assert traps == [symbols['zero_probe']] and symbols['zero_probe'] % 4 == 2 * (batch_index % 2)
    return dict(probes=len(plan), families=counts, register_snapshot_values=len(snapshots),
        guard_reads=len(guards), fcsr_reads=len(fcsrs), permanent_zero_traps=len(traps),
        zero_instruction_phase=symbols['zero_probe'] % 4)


def verifier(plan, batch_index, folder):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        memory = initial_memory(folder / 'test.elf')
        result, controls = inspect(rows, plan, batch_index, symbols, memory), []
        for label, pc, key, bit in [('gpr_snapshot', symbols['snapshot_1_0_1'], 'wdata', 1),
                ('fpr_snapshot', symbols['snapshot_1_1_0'], 'wdata', 1),
                ('fcsr', symbols['fcsr_1'], 'wdata', 16),
                ('zero_cause', symbols['zero_probe'], 'cause', 1),
                ('zero_tval', symbols['zero_probe'], 'tval', 1)]:
            broken = copy.deepcopy(rows)
            row = next(row for row in broken if int(row['pc'], 16) == pc)
            value = int(row[key], 10 if key == 'cause' else 16) ^ bit
            row[key] = str(value) if key == 'cause' else f'{value:016x}'
            try:
                inspect(broken, plan, batch_index, symbols, memory)
            except AssertionError:
                controls.append(label)
            else:
                raise AssertionError(f'Incorrect {label} accepted')
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
        scope='All 394 RV64 base-C HINT code points plus NOP under inert implementation policy; GPR/FPR/FCSR snapshots, two SRAM guards and permanent all-zero illegal trap. Reserved encodings, privilege/FS combinations, all CSRs and microarchitectural hint effects separate',
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
        print('PASS native RVC HINT', index, outcome['probes'], 'probes;',
            outcome['matched_events'], 'Sail/RTL events;', len(outcome['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

"""Native Zimop zero-result and Zcmop no-write contracts, including U mode."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from audit_rv64m_contract import MASK
from run_hv_sail_fixture import run_fixture
from run_rvc_hint_contract import (DEPENDENCIES as C_DEPENDENCIES,
    fixture as c_fixture, verifier as c_verifier)
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/mop_contract'
DEPENDENCIES = [*C_DEPENDENCIES, 'scripts/run_rvc_hint_contract.py']
BATCH, FCSR = 512, 0x65


def cases():
    plan = []
    for kind, count in [('r', 32), ('rr', 8)]:
        for number in range(count):
            for rd in range(32):
                pairs = [(rd + 1) % 32, rd] if kind == 'r' else [
                    ((rd + 1) % 32, (rd + 2) % 32),
                    (rd, (rd + 1) % 32), ((rd + 1) % 32, rd), (rd, rd)]
                for pair in pairs:
                    rs1, rs2 = (pair, None) if kind == 'r' else pair
                    inputs = {rd: MASK} if rd else {}
                    if rs1:
                        inputs[rs1] = (0x8000000000000001 ^ number << 32 ^ rd) & MASK
                    if rs2:
                        inputs[rs2] = inputs[rs1] if rs2 == rs1 else 0x0123456789abcdef ^ rs2
                    plan.append(dict(name=f'{kind}.{number}', kind=kind, number=number,
                        rd=rd, rs1=rs1, rs2=rs2, inputs=inputs))
    return plan


def word(case):
    number = case['number']
    common = case['rd'] << 7 | case['rs1'] << 15
    # Ratified opcode fields: R number at 30/27:26/21:20; RR at 30/27:26.
    if case['kind'] == 'r':
        return 0x81c04073 | (number >> 4) << 30 | ((number >> 2) & 3) << 26 | (number & 3) << 20 | common
    return 0x82004073 | (number >> 2) << 30 | (number & 3) << 26 | case['rs2'] << 20 | common


def roles(case):
    used = {*case['inputs'], case['rd']}
    return [reg for reg in range(6, 14) if reg not in used][:2]


def fixture(plan, mode):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6000', 'csrs mstatus,t0', f'li t0,{FCSR}', 'csrw fcsr,t0']
    if mode == 'U':
        lines += ['li t0,-1', 'csrw pmpaddr0,t0', 'li t0,31', 'csrw pmpcfg0,t0',
            'la t0,user_exit', 'csrw mtvec,t0', 'la t0,user_start', 'csrw mepc,t0',
            'li t0,0x6000', 'csrw mstatus,t0', 'mret', 'user_start:']
    for index, case in enumerate(plan, 1):
        scratch, check = roles(case)
        lines += [f'li x{reg},{value:#x}' for reg, value in case['inputs'].items()]
        lines += [f'probe_{index}:.word {word(case):#x} # mop.{case["name"]}', f'bnez x{case["rd"]},fail']
        for reg, value in case['inputs'].items():
            if reg != case['rd']:
                lines += [f'li x{check},{value:#x}', f'bne x{reg},x{check},fail']
        lines += [f'state_{index}:csrr x{scratch},fcsr', f'li x{check},{FCSR}', f'bne x{scratch},x{check},fail']
    if mode == 'U':
        lines += ['user_done:ecall', 'j fail', '.balign 4', 'user_exit:',
            'csrr t0,mcause', 'li t1,8', 'bne t0,t1,fail',
            'csrr t0,mepc', 'la t1,user_done', 'bne t0,t1,fail']
    lines += ['li t1,1', 'j finish', '.balign 4', 'fail:li t1,3', 'finish:',
        'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt', '.section .tohost,"aw"',
        '.balign 8', '.globl tohost,fromhost', 'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, mode, symbols):
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    states = {symbols[f'state_{i}']: case for i, case in enumerate(plan, 1)}
    registers = [None] * 32
    registers[0] = 0
    seen, state_reads, traps, forms = set(), set(), [], {}
    zero_destinations, aliases = 0, 0
    for index, row in enumerate(rows):
        pc, instruction = int(row['pc'], 16), int(row['instruction'], 16)
        if pc >= 0x80000000 and row['trap'] == '1':
            assert mode == 'U' and pc == symbols['user_done'] and instruction == 0x73
            assert int(row['cause']) == 8 and int(row['tval'], 16) == 0 and row['rd_write'] == '0'
            assert int(rows[index + 1]['pc'], 16) == symbols['user_exit']
            traps.append(pc)
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and row['trap'] == '0' and instruction == word(case)
            for reg, value in case['inputs'].items():
                assert registers[reg] == value, (case, reg, registers[reg])
            if case['rd']:
                assert registers[case['rd']] != 0
                assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == case['rd']
                assert int(row['wdata'], 16) == 0, (case, row)
            else:
                assert row['rd_write'] == '0' or (row['rd_fp'] == '0' and row['rd'] == '0')
                zero_destinations += 1
            assert int(rows[index + 1]['pc'], 16) == pc + 4
            aliases += int(case['rd'] != 0 and case['rd'] in (case['rs1'], case['rs2']))
            forms[case['name']] = forms.get(case['name'], 0) + 1
            seen.add(pc)
        if pc in states:
            scratch = roles(states[pc])[0]
            assert pc not in state_reads and instruction == 3 << 20 | 2 << 12 | scratch << 7 | 0x73
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == scratch
            assert int(row['wdata'], 16) == FCSR
            state_reads.add(pc)
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    assert len(seen) == len(state_reads) == len(plan)
    assert traps == ([symbols['user_done']] if mode == 'U' else [])
    return dict(probes=len(plan), forms=forms, zero_destinations=zero_destinations,
        destination_source_aliases=aliases, checked_fcsr_reads=len(state_reads), user_exit_traps=len(traps))


def verifier(plan, mode, folder):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        result, controls = inspect(rows, plan, mode, symbols), []
        for name in result['forms']:
            case_index = next(i for i, case in enumerate(plan, 1) if case['name'] == name and case['rd'])
            pc = symbols[f'probe_{case_index}']
            broken = copy.deepcopy(rows)
            row = next(row for row in broken if int(row['pc'], 16) == pc)
            row['wdata'] = '0000000000000001'
            try:
                inspect(broken, plan, mode, symbols)
            except AssertionError:
                controls.append(name)
            else:
                raise AssertionError(f'Incorrect MOP zero result accepted: {name}')
        broken = copy.deepcopy(rows)
        row = next(row for row in broken if int(row['pc'], 16) == symbols['state_1'])
        row['wdata'] = f'{FCSR ^ 16:016x}'
        try:
            inspect(broken, plan, mode, symbols)
        except AssertionError:
            controls.append('fcsr')
        else:
            raise AssertionError('Incorrect FCSR accepted')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    plan = cases()
    FOLDER.mkdir(parents=True, exist_ok=True)
    jobs = [(f'M/{index // BATCH}', plan[index:index + BATCH], 'M') for index in range(0, len(plan), BATCH)]
    jobs.append(('U', [case for case in plan if case['rd'] in (0, 5, 31)], 'U'))
    compressed = [dict(name=f'c.mop.{n}', word=0x6001 | n << 7) for n in range(1, 16, 2)]
    jobs.append(('C', compressed, 'C'))
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='Default Zimop/Zcmop behavior without redefining extensions; all 40 MOP forms and destinations with selected source aliases, U subset and all eight compressed forms. Not every register Cartesian product, all privilege states, extension redefinitions or memory-order proof',
        inputs=source_inputs(DEPENDENCIES), cases=[])
    if args.check:
        saved = json.loads((FOLDER / 'report.json').read_bytes())
        assert saved['passed'] and saved['generator_sha256'] == top['generator_sha256']
        assert saved['inputs'] == top['inputs'] and len(saved['cases']) == len(jobs)
    else:
        dump(FOLDER / 'report.json', top)
    for index, (name, batch, mode) in enumerate(jobs):
        folder = FOLDER / name
        folder.mkdir(parents=True, exist_ok=True)
        text = c_fixture(batch, 0) if mode == 'C' else fixture(batch, mode)
        verify = c_verifier(batch, 0, folder) if mode == 'C' else verifier(batch, mode, folder)
        if args.check:
            outcome = check_fixture(folder, __file__, text, verify)
            old = saved['cases'][index]
            assert old['name'] == name and old['report_sha256'] == sha(folder / 'report.json') and old['outcomes'] == outcome
        else:
            source = folder / 'test.S'
            source.write_text(text, encoding='utf-8')
            outcome = run_fixture(source, folder, __file__, verify,
                source_dependencies=DEPENDENCIES, timeout_cycles=3000000)
        top['cases'].append(dict(name=name, report_sha256=sha(folder / 'report.json'), outcomes=outcome))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS native MOP', name, outcome['probes'], 'probes;', outcome['matched_events'],
            'Sail/RTL events;', len(outcome['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

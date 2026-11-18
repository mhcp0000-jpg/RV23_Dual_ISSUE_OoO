"""Native six-form floating CSR alias and reserved-high-bit contract."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs

FOLDER = ROOT / 'out/rva23/fcsr_alias_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py']
BATCH = 256
MASK = (1 << 64) - 1
UPPER = (0, 0xdeadbeef00000100, MASK ^ 255)


def cases():
    plan = []
    for csr in (1, 2, 3):
        for f3 in (1, 2, 3, 5, 6, 7):
            for low in range(32):
                for upper in ((0,) if f3 >= 5 else UPPER):
                    plan.append(dict(csr=csr, f3=f3, value=low | upper))
    for low in range(256):
        for upper in (0, MASK ^ 255):
            plan.append(dict(csr=3, f3=1, value=low | upper))
    assert len(plan) == 1664
    for case in plan:
        case['seed'] = (0xa0 | (31 if case['value'] & 1 else 0)) if case['csr'] == 1 else (
            0x15 | ((7 if case['value'] & 1 else 0) << 5)) if case['csr'] == 2 else None
    return plan


def field(state, csr):
    return state & 31 if csr == 1 else state >> 5 if csr == 2 else state


def update(state, case):
    csr, command, value = case['csr'], case['f3'] & 3, case['value']
    old = field(state, csr)
    raw = value if command == 1 else old | value if command == 2 else old & ~value
    if csr == 1:
        return state & 0xe0 | raw & 31
    if csr == 2:
        return state & 31 | (raw & 7) << 5
    return raw & 255


def encoding(case):
    return case['csr'] << 20 | (case['value'] if case['f3'] >= 5 else 9) << 15 | case['f3'] << 12 | 10 << 7 | 0x73


def fixture(plan):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6000', 'csrs mstatus,t0', 'csrwi fcsr,0']
    state = 0
    for index, case in enumerate(plan, 1):
        if case['seed'] is not None:
            state = case['seed']
            lines += [f'li x12,{state}', 'csrw fcsr,x12']
        lines += [f'li x9,{case["value"]:#x}', f'probe_{index}:.word {encoding(case):#x}',
            f'li x11,{field(state, case["csr"])}', 'bne x10,x11,fail']
        state = update(state, case)
        for csr in (1, 2, 3):
            lines += [f'read_{index}_{csr}:csrr x10,{csr}', f'li x11,{field(state, csr)}', 'bne x10,x11,fail']
    lines += ['li t1,1', 'j finish', 'fail:li t1,3', 'finish:', 'la t0,tohost', 'sd t1,0(t0)',
        'halt:j halt', '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, symbols):
    expected, state = {}, 0
    for index, case in enumerate(plan, 1):
        if case['seed'] is not None:
            state = case['seed']
        expected[symbols[f'probe_{index}']] = (encoding(case), field(state, case['csr']))
        state = update(state, case)
        for csr in (1, 2, 3):
            expected[symbols[f'read_{index}_{csr}']] = (csr << 20 | 2 << 12 | 10 << 7 | 0x73, field(state, csr))
    seen = set()
    for index, row in enumerate(rows):
        pc = int(row['pc'], 16)
        assert pc < 0x80000000 or row['trap'] == '0', row
        if pc in expected:
            word, value = expected[pc]
            assert pc not in seen and int(row['instruction'], 16) == word
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '10'
            assert int(row['wdata'], 16) == value, row
            assert int(rows[index + 1]['pc'], 16) == pc + 4
            seen.add(pc)
    assert seen == set(expected)
    return dict(probes=len(plan), checked_csr_results=len(seen), final_fcsr=state,
        csr_forms=sorted({(case['csr'], case['f3']) for case in plan}))


def verifier(plan, folder):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        result, controls = inspect(rows, plan, symbols), []
        for csr, f3 in result['csr_forms']:
            i = next(i for i, case in enumerate(plan, 1) if (case['csr'], case['f3']) == (csr, f3))
            for suffix in (f'probe_{i}', f'read_{i}_1', f'read_{i}_2', f'read_{i}_3'):
                broken = copy.deepcopy(rows)
                row = next(row for row in broken if int(row['pc'], 16) == symbols[suffix])
                row['wdata'] = f"{int(row['wdata'], 16) ^ 1:016x}"
                try:
                    inspect(broken, plan, symbols)
                except AssertionError:
                    controls.append(f'{csr}:{f3}:{suffix}')
                else:
                    raise AssertionError('Incorrect FP CSR alias result accepted')
        result['csr_forms'] = [list(pair) for pair in result['csr_forms']]
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    plan = cases()
    batches = [plan[start:start + BATCH] for start in range(0, len(plan), BATCH)]
    FOLDER.mkdir(parents=True, exist_ok=True)
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='M-mode FS-enabled six-form fflags/frm/fcsr alias and high-bit masks; all 256 FCSR states written. Reserved frm values stored without executing FP arithmetic. Not all privilege/FS, arithmetic flag accrual, all CSR field side effects or pipeline schedules',
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
            outcome = run_fixture(source, folder, __file__, verify, source_dependencies=DEPENDENCIES, timeout_cycles=3000000)
        top['cases'].append(dict(index=index, report_sha256=sha(folder / 'report.json'), outcomes=outcome))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS native FP CSR aliases', index, outcome['probes'], 'probes;', outcome['matched_events'],
            'Sail/RTL events;', len(outcome['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

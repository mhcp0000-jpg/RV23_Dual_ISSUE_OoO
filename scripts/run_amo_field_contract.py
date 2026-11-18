"""Native AMO W/D aq/rl and register alias matrix with independent byte oracle."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from audit_rv64a_contract import AMO, REQUIRED, inspect as atomic_inspect
from audit_rv64i_compute_control import sx
from audit_rv64i_memory_values import initial_memory
from audit_rv64m_contract import MASK
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs

FOLDER = ROOT / 'out/rva23/amo_field_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/audit_rv64a_contract.py',
    'scripts/audit_rv64i_compute_control.py', 'scripts/audit_rv64i_memory_values.py',
    'scripts/audit_rv64m_contract.py']
BATCH = 256
ALIASES = [(10, 8, 9), (0, 8, 9), (9, 8, 9), (8, 8, 9), (10, 8, 8), (8, 8, 8)]
PATTERNS = [(0, MASK), (MASK, 1), (0x80000000, 0x123456787fffffff),
    (0x8000000000000001, 0x7fffffff80000000)]


def cases():
    plan = []
    for op, name in AMO.items():
        for size in (4, 8):
            for order in range(4):
                for rd, base, source in ALIASES:
                    for old, operand in PATTERNS:
                        address = 0x80090000 + (len(plan) % (64 // size)) * size
                        plan.append(dict(name=name + ('_w' if size == 4 else '_d'), size=size,
                            address=address, old=old, operand=address if base == source else operand,
                            rd=rd, base=base, source=source,
                            word=op << 27 | order << 25 | source << 20 | base << 15
                                | (2 if size == 4 else 3) << 12 | rd << 7 | 0x2f))
    assert len(plan) == 1728
    return plan


def fixture(plan):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0']
    for index, case in enumerate(plan, 1):
        address, size = case['address'], case['size']
        lines += [f'li x16,{address:#x}', f'li x17,{(address & ~7) - 8:#x}',
            'li x18,0xa5a5a5a5a5a5a5a5']
        lines += [f'sd x18,{offset}(x17)' for offset in range(0, 32, 8)]
        lines += [f'li x18,{case["old"]:#x}', f's{"w" if size == 4 else "d"} x18,0(x16)']
        if case['rd'] and case['rd'] not in (case['base'], case['source']):
            lines.append(f'li x{case["rd"]},0x5a5a5a5a5a5a5a5a')
        lines += [f'li x{case["source"]},{case["operand"]:#x}', f'li x{case["base"]},{address:#x}',
            f'probe_{index}:.word {case["word"]:#x}']
        if case['rd']:
            expected = sx(case['old'], size * 8) & MASK
            lines += [f'li x19,{expected:#x}', f'bne x{case["rd"]},x19,fail']
        lines += [f'guard_{index}_{offset}:ld x18,{offset}(x17)' for offset in range(0, 32, 8)]
    lines += ['li t1,1', 'j finish', 'fail:li t1,3', 'finish:',
        'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt', '.section .tohost,"aw"', '.balign 8',
        '.globl tohost,fromhost', 'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, symbols, memory):
    probes = {symbols[f'probe_{i}']: case for i, case in enumerate(plan, 1)}
    guards = {symbols[f'guard_{i}_{offset}']: offset
        for i in range(1, len(plan) + 1) for offset in range(0, 32, 8)}
    seen, observed = set(), set()
    for index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        assert pc < 0x80000000 or row['trap'] == '0', row
        if pc in probes:
            assert pc not in seen and word == probes[pc]['word']
            assert int(rows[index + 1]['pc'], 16) == pc + 4
            seen.add(pc)
        if pc in guards:
            assert pc not in observed and word == guards[pc] << 20 | 17 << 15 | 3 << 12 | 18 << 7 | 3
            observed.add(pc)
    assert seen == set(probes) and observed == set(guards)
    coverage = atomic_inspect(rows, memory)
    assert set(coverage) == {case['name'] for case in plan}
    assert sum(stats['operations'] for stats in coverage.values()) == len(plan)
    assert sum(stats['fully_observed_writes'] for stats in coverage.values()) == len(plan)
    return dict(probes=len(plan), coverage=coverage, guard_reads=len(observed))


def verifier(plan, folder):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        memory = initial_memory(folder / 'test.elf')
        result, controls = inspect(rows, plan, symbols, memory), []
        for name in result['coverage']:
            for kind in ('result', 'memory'):
                index = next(i for i, case in enumerate(plan, 1) if case['name'] == name and case['rd'])
                case = plan[index - 1]
                pc = symbols[f'probe_{index}' if kind == 'result' else f'guard_{index}_8']
                bit = 1 if kind == 'result' else 1 << ((case['address'] & 7) * 8)
                broken = copy.deepcopy(rows)
                row = next(row for row in broken if int(row['pc'], 16) == pc)
                row['wdata'] = f"{int(row['wdata'], 16) ^ bit:016x}"
                try:
                    inspect(broken, plan, symbols, memory)
                except AssertionError:
                    controls.append(name + ':' + kind)
                else:
                    raise AssertionError(f'Incorrect AMO {name} {kind} accepted')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    plan = cases()
    assert {case['name'] for case in plan} == REQUIRED
    batches = [plan[start:start + BATCH] for start in range(0, len(plan), BATCH)]
    FOLDER.mkdir(parents=True, exist_ok=True)
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='Finite M-mode Bare AMO W/D result/memory matrix: all aq/rl encodings, six register alias patterns and four selected operand pairs. Not ordering, all registers/operands, LR/SC, faults, privileges or universal concurrency proof',
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
        print('PASS native AMO fields', index, outcome['probes'], 'probes;', outcome['matched_events'],
            'Sail/RTL events;', len(outcome['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

"""Host/guest FS 0..3 gates on representative FP classes in five modes."""
import argparse
import copy
import itertools
import json

from audit_hv_sail_fixture import check_fixture
from run_fp_integer_contract import labels
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/fp_permission_matrix'
MODES = ('M', 'HS', 'VS', 'U', 'VU')
SENTINEL = 0x7ff8000012345678
ONE, THREE, FOUR, FIVE, SEVEN = (0x3ff0000000000000, 0x4008000000000000,
    0x4010000000000000, 0x4014000000000000, 0x401c000000000000)
OPS = [('fadd', 0x02940553, 'fp', FOUR), ('fmadd', 0x92940543, 'fp', FOUR),
       ('fld', 0x000bb507, 'fp', FIVE), ('fsd', 0x009bb027, 'store', None),
       ('fmv_d_x', 0xf2078553, 'fp', SEVEN), ('fmv_x_d', 0xe2040fd3, 'int', ONE),
       ('fcsr_read', 0x00302ff3, 'int', 5), ('frm_read', 0x00202ff3, 'int', 0),
       ('fflags_read', 0x00102ff3, 'int', 5), ('fflags_write', 0x0010d073, 'csr', None),
       ('fcsr_write', 0x00379ff3, 'int', 5)]
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/run_fp_integer_contract.py',
    'scripts/run_fp_bit_contract.py', 'scripts/audit_rv64i_compute_control.py',
    'scripts/audit_rv64m_contract.py', 'scripts/fp_reference.py']


def cases(mode):
    result = []
    for host_fs, guest_fs, (name, word, kind, value) in itertools.product(range(4), range(4), OPS):
        denied = host_fs == 0 or mode in ('VS', 'VU') and guest_fs == 0
        result.append(dict(id=len(result) + 1, mode=mode, host_fs=host_fs, guest_fs=guest_fs,
            name=name, word=word, kind=kind, value=value, cause=2 if denied else 0,
            ecall={'M': 11, 'HS': 9, 'VS': 10, 'U': 8, 'VU': 8}[mode]))
    return result


def changes_fp_state(case):
    return not case['cause'] and (case['kind'] == 'fp' or case['name'] in ('fflags_write', 'fcsr_write'))


def fixture(mode):
    plan = cases(mode)
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,m_trap', 'csrw mtvec,t0', 'li t0,-1', 'csrw pmpaddr0,t0',
        'li t0,31', 'csrw pmpcfg0,t0', 'csrw medeleg,zero', 'csrw mie,zero',
        'csrw hgatp,zero', 'csrw satp,zero', 'csrw vsatp,zero',
        'li s10,0', 'li a4,0x800a0000', 'mv s7,a4', 'j setup_1']
    privilege = 3 if mode == 'M' else 1 if mode in ('HS', 'VS') else 0
    virtual = mode in ('VS', 'VU')
    for case in plan:
        i, denied = case['id'], bool(case['cause'])
        status = privilege << 11 | int(virtual) << 39 | case['host_fs'] << 13
        expected_fp = case['value'] if not denied and case['kind'] == 'fp' else SENTINEL
        expected_int = case['value'] if not denied and case['kind'] == 'int' else 0x55aa
        expected_mem = THREE if not denied and case['kind'] == 'store' else FIVE
        expected_csr = (1 if case['name'] == 'fflags_write' else 0x65) if not denied and case['name'] in ('fflags_write', 'fcsr_write') else 5
        lines += [f'setup_{i}:', f'li s0,{i}', f'li s1,{case["cause"]}', f'li s2,{case["word"]:#x}',
            f'la s3,probe_{i}', f'la s4,after_{i}', f'la s11,ecall_{i}', f'la s5,capture_{i}',
            'li s6,0', f'li s8,{case["ecall"]}', 'li t0,0x6000', 'csrw mstatus,t0',
            f'li t0,{ONE:#x}', 'fmv.d.x fs0,t0', 'fmv.d.x fs2,t0',
            f'li t0,{THREE:#x}', 'fmv.d.x fs1,t0', f'li t0,{SENTINEL:#x}', 'fmv.d.x fa0,t0',
            'csrwi fcsr,5', f'li t0,{FIVE:#x}', 'sd t0,0(a4)', 'li t6,0x55aa',
            f'li a5,{0x65 if case["name"] == "fcsr_write" else SEVEN:#x}',
            f'li t0,{case["guest_fs"] << 13}', 'csrw vsstatus,t0',
            f'li t0,{status}', 'csrw mstatus,t0']
        lines += [f'j probe_{i}'] if mode == 'M' else [f'la t0,probe_{i}', 'csrw mepc,t0', 'mret']
        lines += [f'probe_{i}: .word {case["word"]:#x} # {case["name"]}',
            f'after_{i}:', f'ecall_{i}: ecall', 'j fail', f'capture_{i}:']
        if changes_fp_state(case):
            lines += [f'host_state_{i}: csrr t0,mstatus', 'bgez t0,fail',
                'srli t0,t0,13', 'andi t0,t0,3', 'li t1,3', 'bne t0,t1,fail']
            if virtual:
                lines += [f'guest_state_{i}: csrr t0,vsstatus', 'bgez t0,fail',
                    'srli t0,t0,13', 'andi t0,t0,3', 'li t1,3', 'bne t0,t1,fail']
        lines += ['li t0,0x6000', 'csrw mstatus,t0', f'post_{i}:',
            'csrr t0,fcsr', f'li t1,{expected_csr}', 'bne t0,t1,fail',
            'fmv.x.d t0,fa0', f'li t1,{expected_fp:#x}', 'bne t0,t1,fail',
            f'li t1,{expected_int:#x}', 'bne t6,t1,fail', 'ld t0,0(a4)',
            f'li t1,{expected_mem:#x}', 'bne t0,t1,fail', 'addi s10,s10,1',
            f'j {"finish" if i == len(plan) else "setup_" + str(i + 1)}']
    lines += ['m_trap:', 'csrr t0,mcause', 'beq t0,s8,case_done', 'beqz s1,fail',
        'bne t0,s1,fail', 'bnez s6,fail', 'csrr t0,mtval', 'bne t0,s2,fail',
        'csrr t0,mepc', 'bne t0,s3,fail', 'li s6,1', 'csrw mepc,s4', 'mret',
        'case_done:', 'csrr t0,mepc', 'bne t0,s11,fail', 'snez t0,s1', 'bne t0,s6,fail',
        'jr s5', 'finish:', f'li t0,{len(plan)}',
        'bne s10,t0,fail', 'li t1,1', 'j finish_host', 'fail:', 'slli t1,s0,1',
        'ori t1,t1,1', 'finish_host:', 'la t0,tohost', 'sd t1,0(t0)', 'halt: j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def inspect(rows, mode, symbols):
    plan = cases(mode)
    probes = {symbols[f'probe_{case["id"]}']: case for case in plan}
    ecalls = {symbols[f'ecall_{case["id"]}']: case for case in plan}
    states = {symbols[f'host_state_{case["id"]}']: 'host' for case in plan if changes_fp_state(case)}
    if mode in ('VS', 'VU'):
        states.update({symbols[f'guest_state_{case["id"]}']: 'guest' for case in plan if changes_fp_state(case)})
    seen, exits, state_reads, traps = set(), set(), set(), []
    for row in rows:
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and word == case['word'], row
            seen.add(pc)
            assert (row['trap'] == '1') == bool(case['cause']), (case, row)
            if case['cause']:
                assert int(row['cause']) == 2 and int(row['tval'], 16) == word and row['rd_write'] == '0'
            elif case['kind'] in ('fp', 'int'):
                assert row['rd_write'] == '1' and int(row['rd_fp']) == (case['kind'] == 'fp')
                assert int(row['rd']) == (10 if case['kind'] == 'fp' else 31)
                assert int(row['wdata'], 16) == case['value'], (case, row)
            else:
                assert row['rd_write'] == '0' or row['rd_fp'] == '0' and row['rd'] == '0'
        if pc in ecalls:
            case = ecalls[pc]
            assert pc not in exits and word == 0x73 and row['trap'] == '1'
            assert int(row['cause']) == case['ecall'] and int(row['tval'], 16) == 0
            exits.add(pc)
        if pc in states:
            assert pc not in state_reads and row['trap'] == '0'
            assert word == (0x300022f3 if states[pc] == 'host' else 0x200022f3)
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '5'
            value = int(row['wdata'], 16)
            assert (value >> 13) & 3 == 3 and value >> 63 == 1, row
            state_reads.add(pc)
        if pc >= 0x80000000 and row['trap'] == '1':
            assert pc in probes or pc in ecalls, row
            traps.append((pc, int(row['cause'])))
    expected = []
    for case in plan:
        if case['cause']:
            expected.append((symbols[f'probe_{case["id"]}'], 2))
        expected.append((symbols[f'ecall_{case["id"]}'], case['ecall']))
    assert traps == expected and len(seen) == len(exits) == len(plan) and state_reads == set(states)
    return dict(probes=len(plan), legal=sum(not case['cause'] for case in plan),
        illegal=sum(bool(case['cause']) for case in plan), precise_traps=len(traps),
        host_fs_values=list(range(4)), guest_fs_values=list(range(4)), mode=mode,
        host_dirty_readbacks=sum(value == 'host' for value in states.values()),
        guest_dirty_readbacks=sum(value == 'guest' for value in states.values()))


def verifier(mode, folder):
    def verify(sail_trace, rtl_trace):
        actual = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), actual)
        assert mismatch is None, mismatch
        symbols = labels(folder)
        result = inspect(actual, mode, symbols)
        controls = []
        for name, _, _, _ in OPS:
            case = next(case for case in cases(mode) if case['name'] == name and case['cause'])
            for field, wrong in [('cause', '22'), ('tval', '0000000000000000')]:
                broken = copy.deepcopy(actual)
                row = next(row for row in broken if int(row['pc'], 16) == symbols[f'probe_{case["id"]}'])
                row[field] = wrong
                try:
                    inspect(broken, mode, symbols)
                except AssertionError:
                    controls.append(dict(name=name, field=field))
                else:
                    raise AssertionError(f'Incorrect {name} {field} accepted')
        case = next(case for case in cases(mode) if changes_fp_state(case))
        for bank in ('host', 'guest') if mode in ('VS', 'VU') else ('host',):
            broken = copy.deepcopy(actual)
            row = next(row for row in broken if int(row['pc'], 16) == symbols[f'{bank}_state_{case["id"]}'])
            row['wdata'] = f"{int(row['wdata'], 16) ^ (1 << 14):016x}"
            try:
                inspect(broken, mode, symbols)
            except AssertionError:
                controls.append(dict(name='dirty', field=bank))
            else:
                raise AssertionError(f'Incorrect {bank} FS accepted')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='Finite M/HS/VS/U/VU FS enable gates, state preservation and Dirty propagation for changed FP state; imprecise Dirty on non-writers allowed; delegation, permission-fault and scheduling combinations separate',
        inputs=source_inputs(DEPENDENCIES), cases=[])
    if args.check:
        saved = json.loads((FOLDER / 'report.json').read_bytes())
        assert saved['passed'] and saved['generator_sha256'] == top['generator_sha256']
        assert saved['inputs'] == top['inputs'] and len(saved['cases']) == len(MODES)
    else:
        dump(FOLDER / 'report.json', top)
    for mode in MODES:
        folder = FOLDER / mode
        folder.mkdir(exist_ok=True)
        source, verify = folder / 'test.S', verifier(mode, folder)
        if args.check:
            assert json.loads((folder / 'cases.json').read_bytes()) == cases(mode)
            outcomes = check_fixture(folder, __file__, fixture(mode), verify)
            old = next(case for case in saved['cases'] if case['mode'] == mode)
            assert old['report_sha256'] == sha(folder / 'report.json') and old['outcomes'] == outcomes
        else:
            source.write_text(fixture(mode), encoding='utf-8')
            dump(folder / 'cases.json', cases(mode))
            outcomes = run_fixture(source, folder, __file__, verify,
                source_dependencies=[*DEPENDENCIES, (folder / 'cases.json').relative_to(ROOT).as_posix()],
                timeout_cycles=2000000)
        top['cases'].append(dict(mode=mode, report_sha256=sha(folder / 'report.json'), outcomes=outcomes))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS native FP permission', mode, outcomes['probes'], 'probes;',
            outcomes['illegal'], 'FS denials;', outcomes['matched_events'], 'Sail/RTL events', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

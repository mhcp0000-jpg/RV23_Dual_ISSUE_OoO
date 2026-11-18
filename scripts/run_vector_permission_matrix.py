"""Five-mode vector FP/integer/CSR FS/VS permission and Dirty matrix."""
import argparse
import copy
import itertools
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs

FOLDER = ROOT / 'out/rva23/vector_permission_matrix'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py']
MODES = ('M', 'HS', 'VS', 'U', 'VU')
OPS = [('fp', 0x030c1457), ('integer', 0x030c0457), ('csr', 0xc2202ff3)]
SENTINEL = 0xa5a5a5a5a5a5a5a5


def cases(mode):
    # Every Off/on gate pattern at each nonzero state. Mixed nonzero levels
    # across the four fields are intentionally outside this finite matrix.
    states = sorted({tuple(level if bit else 0 for bit in bits)
        for level in (1, 2, 3) for bits in itertools.product(range(2), repeat=4)})
    assert len(states) == 46
    result = []
    for (host_fs, host_vs, guest_fs, guest_vs), (kind, word) in itertools.product(states, OPS):
        virtual = mode in ('VS', 'VU')
        allowed = bool(host_vs and (not virtual or guest_vs))
        if kind == 'fp':
            allowed = allowed and bool(host_fs and (not virtual or guest_fs))
        result.append(dict(id=len(result) + 1, mode=mode, host_fs=host_fs, host_vs=host_vs,
            guest_fs=guest_fs, guest_vs=guest_vs, kind=kind, word=word, cause=0 if allowed else 2,
            ecall={'M': 11, 'HS': 9, 'VS': 10, 'U': 8, 'VU': 8}[mode]))
    assert len(result) == 138
    return result


def changes_vector(case):
    return not case['cause'] and case['kind'] != 'csr'


def expected(case):
    lane = 0x7fc00000 if case['kind'] == 'fp' else 0xbf000001
    vector = lane | lane << 32 if changes_vector(case) else SENTINEL
    return vector, 21 if not case['cause'] and case['kind'] == 'fp' else 5


def fixture(mode):
    plan = cases(mode)
    privilege = 3 if mode == 'M' else 1 if mode in ('HS', 'VS') else 0
    virtual = mode in ('VS', 'VU')
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,m_trap', 'csrw mtvec,t0', 'li t0,-1', 'csrw pmpaddr0,t0',
        'li t0,31', 'csrw pmpcfg0,t0', 'csrw medeleg,zero', 'csrw mie,zero',
        'csrw hgatp,zero', 'csrw satp,zero', 'csrw vsatp,zero', 'li s10,0', 'j setup_1']
    for case in plan:
        i = case['id']
        status = privilege << 11 | int(virtual) << 39 | case['host_fs'] << 13 | case['host_vs'] << 9
        vector, flags = expected(case)
        lines += [f'setup_{i}:', f'li s0,{i}', f'li s1,{case["cause"]}', f'li s2,{case["word"]:#x}',
            f'la s3,probe_{i}', f'la s4,after_{i}', f'la s5,capture_{i}', 'li s6,0', f'li s8,{case["ecall"]}',
            'li t0,0x6600', 'csrw mstatus,t0', 'csrwi vstart,0', 'vsetivli zero,4,e32,m1,tu,mu',
            'la t0,input_a', 'vl1re8.v v16,(t0)', 'la t0,input_b', 'vl1re8.v v24,(t0)',
            'la t0,initial', 'vl1re8.v v8,(t0)', 'csrwi fcsr,5', 'li t6,0x55aa',
            f'li t0,{case["guest_fs"] << 13 | case["guest_vs"] << 9}', 'csrw vsstatus,t0',
            f'li t0,{status}', 'csrw mstatus,t0']
        lines += [f'j probe_{i}'] if mode == 'M' else [f'la t0,probe_{i}', 'csrw mepc,t0', 'mret']
        lines += [f'probe_{i}:.word {case["word"]:#x}', f'after_{i}:', f'ecall_{i}:ecall', 'j fail', f'capture_{i}:']
        if changes_vector(case):
            lines += [f'host_state_{i}:csrr t0,mstatus', 'bgez t0,fail',
                'srli t1,t0,9', 'andi t1,t1,3', 'li t2,3', 'bne t1,t2,fail']
            if case['kind'] == 'fp':
                lines += ['srli t1,t0,13', 'andi t1,t1,3', 'bne t1,t2,fail']
            if virtual:
                lines += [f'guest_state_{i}:csrr t0,vsstatus', 'bgez t0,fail',
                    'srli t1,t0,9', 'andi t1,t1,3', 'bne t1,t2,fail']
                if case['kind'] == 'fp':
                    lines += ['srli t1,t0,13', 'andi t1,t1,3', 'bne t1,t2,fail']
        lines += ['li t0,0x6600', 'csrw mstatus,t0', f'flags_{i}:csrr t2,fcsr',
            f'li t3,{flags}', 'bne t2,t3,fail', f'integer_{i}:mv t2,t6',
            f'li t3,{16 if not case["cause"] and case["kind"] == "csr" else 0x55aa}', 'bne t2,t3,fail',
            'la t0,observed', 'vs1r.v v8,(t0)']
        for offset in (0, 8):
            lines += [f'word_{i}_{offset}:ld t2,{offset}(t0)', f'li t3,{vector:#x}', 'bne t2,t3,fail']
        lines += ['addi s10,s10,1', f'j {"finish" if i == len(plan) else "setup_" + str(i + 1)}']
    lines += ['m_trap:', 'csrr t0,mcause', 'beq t0,s8,case_done', 'beqz s1,fail',
        'bne t0,s1,fail', 'bnez s6,fail', 'csrr t0,mtval', 'bne t0,s2,fail',
        'csrr t0,mepc', 'bne t0,s3,fail', 'li s6,1', 'csrw mepc,s4', 'mret',
        'case_done:', 'csrr t0,mepc', 'bne t0,s4,fail', 'snez t0,s1', 'bne t0,s6,fail', 'jr s5',
        'finish:', f'li t0,{len(plan)}', 'bne s10,t0,fail', 'li t1,1', 'j finish_host',
        'fail:', 'slli t1,s0,1', 'ori t1,t1,1', 'finish_host:', 'la t0,tohost', 'sd t1,0(t0)',
        'halt:j halt', '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0', '.section .bss,"aw",@nobits', '.balign 16', 'observed:.space 16',
        '.section .rodata,"a"', '.balign 16', 'input_a:.fill 4,4,0x7f800001',
        'input_b:.fill 4,4,0x3f800000', 'initial:.fill 16,1,0xa5']
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, symbols):
    probes = {symbols[f'probe_{case["id"]}']: case for case in plan}
    reads, states = {}, {}
    for case in plan:
        i, (vector, flags) = case['id'], expected(case)
        reads[symbols[f'flags_{i}']] = (0x003023f3, flags)
        reads[symbols[f'integer_{i}']] = (31 << 15 | 7 << 7 | 0x13,
            16 if not case['cause'] and case['kind'] == 'csr' else 0x55aa)
        for offset in (0, 8):
            reads[symbols[f'word_{i}_{offset}']] = (offset << 20 | 5 << 15 | 3 << 12 | 7 << 7 | 3, vector)
        if changes_vector(case):
            states[symbols[f'host_state_{i}']] = (0x300, case['kind'] == 'fp')
            if case['mode'] in ('VS', 'VU'):
                states[symbols[f'guest_state_{i}']] = (0x200, case['kind'] == 'fp')
    seen, observed, dirty, traps = set(), set(), set(), []
    for index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if pc >= 0x80000000 and row['trap'] == '1':
            traps.append((pc, int(row['cause'])))
        if pc in probes:
            case = probes[pc]
            assert pc not in seen and word == case['word'] and (row['trap'] == '1') == bool(case['cause'])
            if case['cause']:
                assert int(row['cause']) == 2 and int(row['tval'], 16) == word and row['rd_write'] == '0'
                assert int(rows[index + 1]['pc'], 16) == symbols['m_trap']
            else:
                assert int(rows[index + 1]['pc'], 16) == pc + 4
                if case['kind'] == 'csr':
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '31' and int(row['wdata'], 16) == 16
            seen.add(pc)
        if pc in reads:
            instruction, value = reads[pc]
            assert pc not in observed and word == instruction and row['trap'] == '0'
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '7'
            assert int(row['wdata'], 16) == value, row
            observed.add(pc)
        if pc in states:
            csr, floating = states[pc]
            assert pc not in dirty and word == csr << 20 | 2 << 12 | 5 << 7 | 0x73
            assert row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '5'
            value = int(row['wdata'], 16)
            assert value >> 63 == 1 and (value >> 9) & 3 == 3
            if floating:
                assert (value >> 13) & 3 == 3
            dirty.add(pc)
    assert seen == set(probes) and observed == set(reads) and dirty == set(states)
    expected_traps = []
    for case in plan:
        if case['cause']:
            expected_traps.append((symbols[f'probe_{case["id"]}'], 2))
        expected_traps.append((symbols[f'ecall_{case["id"]}'], case['ecall']))
    assert traps == expected_traps
    return dict(probes=len(plan), allowed=sum(not case['cause'] for case in plan),
        denied=sum(bool(case['cause']) for case in plan), checked_post_results=len(reads),
        dirty_state_reads=len(states), precise_traps=len(traps))


def verifier(mode, folder):
    plan = cases(mode)
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        result, controls = inspect(rows, plan, symbols), []
        for kind, _ in OPS:
            for denied in (False, True):
                case = next(case for case in plan if case['kind'] == kind and bool(case['cause']) == denied)
                name = f'word_{case["id"]}_0'
                broken = copy.deepcopy(rows)
                row = next(row for row in broken if int(row['pc'], 16) == symbols[name])
                row['wdata'] = f"{int(row['wdata'], 16) ^ 1:016x}"
                try:
                    inspect(broken, plan, symbols)
                except AssertionError:
                    controls.append(name)
                else:
                    raise AssertionError('Incorrect vector post-state accepted')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        inputs=source_inputs(DEPENDENCIES), cases=[], scope='Five-mode representative vector FP/integer/vlenb operations; every Off/on host/guest FS/VS gate pattern repeated with Initial/Clean/Dirty nonzero states. Not full mixed-nonzero Cartesian product, all opcodes, delegation, page/PMP faults or every schedule')
    if args.check:
        saved = json.loads((FOLDER / 'report.json').read_bytes())
        assert saved['passed'] and saved['generator_sha256'] == top['generator_sha256'] and saved['inputs'] == top['inputs']
        assert len(saved['cases']) == len(MODES)
    for index, mode in enumerate(MODES):
        folder = FOLDER / mode
        folder.mkdir(exist_ok=True)
        source, verify = folder / 'test.S', verifier(mode, folder)
        if args.check:
            outcome = check_fixture(folder, __file__, fixture(mode), verify)
            old = saved['cases'][index]
            assert old['mode'] == mode and old['report_sha256'] == sha(folder / 'report.json') and old['outcomes'] == outcome
        else:
            source.write_text(fixture(mode), encoding='utf-8')
            outcome = run_fixture(source, folder, __file__, verify, source_dependencies=DEPENDENCIES, timeout_cycles=4000000)
        top['cases'].append(dict(mode=mode, report_sha256=sha(folder / 'report.json'), outcomes=outcome))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS vector FS/VS permissions', mode, outcome, flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

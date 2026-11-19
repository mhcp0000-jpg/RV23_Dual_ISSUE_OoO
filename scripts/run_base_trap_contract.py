"""Same-ELF five-mode base synchronous traps, delegation and non-retirement."""
import argparse
import copy
import subprocess

from audit_hv_sail_fixture import check_fixture
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT

FOLDER = ROOT / 'out/rva23/base_trap_contract'
MODES = ('M', 'HS', 'U', 'VS', 'VU')
FORMS = [('ecall', 0x73, 4), ('ebreak', 0x100073, 4),
         ('c.ebreak', 0x9002, 2), ('illegal32', 0xffffffff, 4), ('illegal16', 0, 2)]


def cases():
    plan = []
    for mode in MODES:
        for md, hd in ((0, 0), (0, 1), (1, 0), (1, 1)):
            for name, word, length in FORMS:
                cause = {'M': 11, 'HS': 9, 'U': 8, 'VS': 10, 'VU': 8}[mode] if name == 'ecall' else (3 if 'break' in name else 2)
                target = 'M' if mode == 'M' or not md else ('VS' if mode in ('VS', 'VU') and hd and cause not in (9, 10, 11) else 'HS')
                plan.append(dict(id=len(plan)+1, mode=mode, md=md, hd=hd, name=name,
                    word=word, length=length, cause=cause, target=target))
    assert len(plan) == 100
    return plan


def fixture(plan):
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'li t0,-1', 'csrw pmpaddr0,t0', 'li t0,31', 'csrw pmpcfg0,t0',
        'csrw mie,zero', 'csrw satp,zero', 'csrw vsatp,zero', 'csrw hgatp,zero',
        'csrw mcountinhibit,zero', 'li t0,7', 'csrw mcounteren,t0', 'csrw scounteren,t0',
        'csrw hcounteren,t0', 'j setup_1']
    for c in plan:
        i, mode = c['id'], c['mode']
        priv = 3 if mode == 'M' else 1 if mode in ('HS', 'VS') else 0
        virtual = mode in ('VS', 'VU')
        lines += [f'setup_{i}:', f'li s0,{i}', f'li s1,{c["cause"]}',
            f'la s3,probe_{i}', f'la s4,after_{i}', f'la s5,capture_{i}', f'la s8,escape_{i}',
            f'li s6,{("M", "HS", "VS").index(c["target"])}', 'li s7,0', 'li s9,0',
            'li a0,0x12345678', 'li ra,0x5678',
            'la t0,m_trap', 'csrw mtvec,t0', 'la t0,hs_trap', 'csrw stvec,t0',
            'la t0,vs_trap', 'csrw vstvec,t0',
            f'li t0,{c["md"] << c["cause"]}', 'csrw medeleg,t0',
            f'li t0,{c["hd"] << c["cause"]}', 'csrw hedeleg,t0',
            'csrw hstatus,zero', 'csrw vsstatus,zero',
            f'li t0,{priv << 11 | int(virtual) << 39}', 'csrw mstatus,t0']
        lines += [f'la s2,probe_{i}'] if c['cause'] == 3 else [f'li s2,{c["word"] if c["cause"] == 2 else 0}']
        if mode == 'M':
            lines += [f'j before_{i}']
        else:
            lines += [f'la t0,before_{i}', 'csrw mepc,t0', 'mret']
        lines += [f'before_{i}:csrr t6,instret',
            f'probe_{i}:{".hword" if c["length"] == 2 else ".word"} {c["word"]:#x}',
            f'after_{i}:addi s9,s9,1', f'escape_{i}:.word {0x73 if c["cause"] == 2 else 0xffffffff:#x}', 'j fail',
            f'capture_{i}:', 'li t0,1', 'bne s7,t0,fail', 'bne s9,t0,fail',
            f'value_{i}_a:mv t2,a0', 'li t3,0x12345678', 'bne t2,t3,fail',
            f'value_{i}_ra:mv t2,ra', 'li t3,0x5678', 'bne t2,t3,fail',
            f'j {"finish" if i == len(plan) else "setup_"+str(i+1)}']
    for target, prefix in [('M', 'm'), ('HS', 's'), ('VS', 's')]:
        label = {'M': 'm_trap', 'HS': 'hs_trap', 'VS': 'vs_trap'}[target]
        lines += ['.balign 4', f'{label}:csrr t2,instret']
        if target == 'M':
            lines += ['csrr t0,mepc', 'beq t0,s8,case_done']
        lines += [f'li t0,{("M", "HS", "VS").index(target)}', 'bne t0,s6,fail',
            f'csrr t0,{prefix}cause', 'bne t0,s1,fail', f'csrr t0,{prefix}epc', 'bne t0,s3,fail',
            f'csrr t0,{prefix}tval', 'bne t0,s2,fail', 'bnez s7,fail',
            'sub t2,t2,t6', 'li t0,1', 'bne t2,t0,fail', 'li s7,1',
            f'csrw {prefix}epc,s4', 'mret' if target == 'M' else 'sret']
    lines += ['case_done:', 'li t0,1', 'bne s7,t0,fail', 'bne s9,t0,fail', 'jr s5',
        'finish:li t1,1', 'j finish_host', 'fail:slli t1,s0,1', 'ori t1,t1,1',
        'finish_host:la t0,tohost', 'sd t1,0(t0)', 'halt:j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost', 'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines)+'\n'


def inspect(rows, plan, symbols):
    probes = {symbols[f'probe_{c["id"]}']: c for c in plan}
    escapes = {symbols[f'escape_{c["id"]}']: c for c in plan}
    seen, escaped, values, counters = set(), set(), set(), 0
    observations = {symbols[f'value_{c["id"]}_{name}']: value for c in plan for name, value in [('a', 0x12345678), ('ra', 0x5678)]}
    for n, row in enumerate(rows):
        pc = int(row['pc'], 16)
        if row['trap'] == '1' and pc >= 0x80000000:
            assert pc in probes or pc in escapes, row
        if pc in probes:
            c = probes[pc]
            assert pc not in seen and row['trap'] == '1' and row['rd_write'] == '0'
            assert int(row['instruction'],16) == c['word'] and int(row['cause']) == c['cause']
            assert int(row['tval'],16) == (pc if c['cause'] == 3 else c['word'] if c['cause'] == 2 else 0)
            label = {'M': 'm_trap', 'HS': 'hs_trap', 'VS': 'vs_trap'}[c['target']]
            assert int(rows[n+1]['pc'],16) == symbols[label]
            # The only retired instruction between these counter samples is the
            # first CSR read itself; the synchronous exception must not retire.
            before = rows[n-1]
            assert int(before['pc'],16) == symbols[f'before_{c["id"]}']
            assert int(before['instruction'],16) == 0xc0202ff3 and before['rd_write'] == '1' and before['trap'] == '0'
            assert int(rows[n+1]['instruction'],16) == 0xc02023f3 and rows[n+1]['rd_write'] == '1' and rows[n+1]['trap'] == '0'
            assert (int(rows[n+1]['wdata'],16)-int(before['wdata'],16)) & ((1<<64)-1) == 1
            counters += 1
            seen.add(pc)
        if pc in escapes:
            c = escapes[pc]
            word = 0x73 if c['cause'] == 2 else 0xffffffff
            cause = {'M':11,'HS':9,'U':8,'VS':10,'VU':8}[c['mode']] if c['cause'] == 2 else 2
            assert pc not in escaped and row['trap'] == '1' and row['rd_write'] == '0'
            assert int(row['instruction'],16) == word and int(row['cause']) == cause
            assert int(row['tval'],16) == (0 if c['cause'] == 2 else word)
            assert int(rows[n+1]['pc'],16) == symbols['m_trap']
            escaped.add(pc)
        if pc in observations:
            assert pc not in values and row['trap'] == '0' and row['rd_write'] == '1'
            assert int(row['wdata'],16) == observations[pc]
            values.add(pc)
    assert seen == set(probes) and escaped == set(escapes) and values == set(observations)
    traps = [r for r in rows if r['trap'] == '1' and int(r['pc'],16) >= 0x80000000]
    assert len(traps) == 2*len(plan)
    return dict(cases=len(seen), counter_pairs=counters, preserved_values=len(values), traps=len(traps),
        routes={t:sum(c['target']==t for c in plan) for t in ('M','HS','VS')})


def verifier(plan):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        sail_rows = read_csv(sail_trace)
        # Native boot executes before this ELF; Sail starts at its entry point.
        # Compare counter deltas independently, not absolute instret origins.
        normalized = []
        for trace in (sail_rows, rows):
            trace = copy.deepcopy(trace)
            for row in trace:
                if int(row['instruction'], 16) & 0xfffff07f == 0xc0202073:
                    row['wdata'] = '0000000000000000'
            normalized.append(trace)
        matched, mismatch = compare(*normalized)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC/'riscv-none-elf-nm.exe'), '-n', str(FOLDER/'test.elf')], text=True)
        symbols = {p[2]:int(p[0],16) for line in nm.splitlines() if len(p:=line.split())==3}
        result, controls = inspect(rows, plan, symbols), []
        for c in plan:
            n = next(n for n,r in enumerate(sail_rows) if int(r['pc'],16)==symbols[f'probe_{c["id"]}'])
            assert (int(sail_rows[n+1]['wdata'],16)-int(sail_rows[n-1]['wdata'],16)) & ((1<<64)-1) == 1
        for kind in ('cause', 'tval', 'destination', 'handler', 'instret', 'preserved'):
            broken = copy.deepcopy(rows)
            n = next(n for n,r in enumerate(broken) if int(r['pc'],16)==symbols['probe_1'])
            if kind=='cause': broken[n]['cause']='2'
            elif kind=='tval': broken[n]['tval']='0000000000000001'
            elif kind=='destination': broken[n]['rd_write']='1'
            elif kind=='handler': broken[n+1]['pc']=f'{symbols["hs_trap"]:016x}'
            elif kind=='instret': broken[n+1]['wdata']=f'{int(broken[n+1]["wdata"],16)+1:016x}'
            else:
                r=next(r for r in broken if int(r['pc'],16)==symbols['value_1_a'])
                r['wdata']='0000000000000000'
            try: inspect(broken, plan, symbols)
            except AssertionError: controls.append(kind)
            else: raise AssertionError('Invalid base trap evidence accepted')
        return dict(**result, matched_events=matched, rejected_mutations=controls)
    return verify


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    plan=cases()
    FOLDER.mkdir(parents=True,exist_ok=True)
    source=FOLDER/'test.S'
    if args.check:
        result=check_fixture(FOLDER,__file__,fixture(plan),verifier(plan))
    else:
        source.write_text(fixture(plan),encoding='utf-8')
        result=run_fixture(source,FOLDER,__file__,verifier(plan),source_dependencies=['scripts/audit_hv_sail_fixture.py'],timeout_cycles=1000000)
    print('PASS base trap contract',result,flush=True)


if __name__=='__main__':
    main()

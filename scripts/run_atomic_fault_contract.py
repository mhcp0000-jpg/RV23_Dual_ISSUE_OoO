"""Native M/HS/U atomic alignment/PMP/PMA priority and precise no-write cases."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha

FOLDER=ROOT/'out/rva23/atomic_fault_contract'
MODES=('M','HS','U')
OPS=(2,3,0,1,4,8,12,16,20,24,28)
INITIAL=0x8123456789abcdef
OPERAND=0x1020304076543210
MASK=(1<<64)-1


def memory_value(op,shape):
    bits=32 if shape else 64;shift=32 if shape==2 else 0;mask=(1<<bits)-1
    a=(INITIAL>>shift)&mask;b=OPERAND&mask
    sx=lambda x:x-(1<<bits) if x>>(bits-1) else x
    if op==2:return (sx(a) if shape else a)&MASK,INITIAL
    if op==3:return 1,INITIAL
    value={0:lambda:a+b,1:lambda:b,4:lambda:a^b,8:lambda:a|b,12:lambda:a&b,
        16:lambda:min(sx(a),sx(b)),20:lambda:max(sx(a),sx(b)),24:lambda:min(a,b),28:lambda:max(a,b)}[op]()&mask
    return (sx(a) if shape else a)&MASK,(INITIAL&~(mask<<shift))|(value<<shift)


def cases(mode):
    plan=[]
    for shape in range(3):
        for op in OPS:
            contexts=[('sram',perm,bad) for perm in (0,1,3,5) for bad in (0,1)]
            if op in (2,3,0):contexts += [(kind,7,bad) for kind in ('mmio','high') for bad in (0,1)]
            for kind,perm,bad in contexts:
                base={'sram':0x800a0000,'mmio':0x02000000,'high':0x1800a0000}[kind]
                address=base+(4 if shape==2 else 0)+bad
                allowed=mode=='M' or (bool(perm&1) if op==2 else bool(perm&2) if op==3 else perm&3==3)
                cause=(4 if op==2 else 6) if bad else (5 if op==2 else 7) if kind!='sram' or not allowed else 0
                result,memory=memory_value(op,shape)
                if cause:result,memory=0x55aa,INITIAL
                word=op<<27 | (0 if op==2 else 9)<<20 | 8<<15 | (2 if shape else 3)<<12 | 7<<7 | 0x2f
                plan.append(dict(id=len(plan)+1,shape=shape,op=op,kind=kind,perm=perm,address=address,
                    cause=cause,word=word,result=result,memory=memory))
    assert len(plan)==300
    return plan


def fixture(mode):
    lines=['.section .text.init,"ax"','.option norvc','.globl _start','_start:',
        'la t0,m_trap','csrw mtvec,t0','csrw medeleg,zero','csrw mie,zero','csrw satp,zero',
        'li t0,0x800a0000','srli t0,t0,2','csrw pmpaddr0,t0','li t0,-1','csrw pmpaddr1,t0']
    for c in cases(mode):
        i=c['id']
        lines += [f'setup_{i}:',f'li s4,{i}',f'li s2,{c["cause"]}',f'la s3,probe_{i}',f'la s5,after_{i}',f'la s6,capture_{i}',
            'li s7,0',f'li s8,{c["address"]:#x}',f'li s9,{ {"M":11,"HS":9,"U":8}[mode]}',
            f'li t0,{0x1f00|0x18|c["perm"]}', 'csrw pmpcfg0,t0',
            'li s10,0x800a0000',f'li t0,{INITIAL:#x}','sd t0,0(s10)',
            'li t0,0x800a0040','sc.d zero,zero,(t0)',f'li s0,{c["address"]:#x}',f'li s1,{OPERAND:#x}','li t2,0x55aa',
            f'li t0,{ {"M":3,"HS":1,"U":0}[mode]<<11}','csrw mstatus,t0']
        lines += [f'j probe_{i}'] if mode=='M' else [f'la t0,probe_{i}','csrw mepc,t0','mret']
        lines += [f'probe_{i}:.word {c["word"]:#x}',f'after_{i}:ecall','j fail',f'capture_{i}:',
            f'value_{i}:mv a0,t2',f'li t3,{c["result"]:#x}','bne a0,t3,fail',
            f'guard_{i}:ld a0,0(s10)',f'li t3,{c["memory"]:#x}','bne a0,t3,fail']
    lines += ['li t1,1','j finish','m_trap:','csrr t0,mcause','beq t0,s9,case_done','beqz s2,fail',
        'bne t0,s2,fail','bnez s7,fail','csrr t0,mepc','bne t0,s3,fail','csrr t0,mtval','bne t0,s8,fail',
        'li s7,1','csrw mepc,s5','mret','case_done:','csrr t0,mepc','bne t0,s5,fail',
        'snez t0,s2','bne t0,s7,fail','jr s6','fail:slli t1,s4,1','ori t1,t1,1',
        'finish:la t0,tohost','sd t1,0(t0)','halt:j halt','.section .tohost,"aw"','.balign 8',
        '.globl tohost,fromhost','tohost:.dword 0','fromhost:.dword 0']
    return '\n'.join(lines)+'\n'


def inspect(rows,plan,labels):
    probes={labels[f'probe_{c["id"]}']:c for c in plan}
    reads={labels[f'{kind}_{c["id"]}']:c['result' if kind=='value' else 'memory'] for c in plan for kind in ('value','guard')}
    seen=set();observed=set();faults=0;results=0
    for n,row in enumerate(rows):
        pc=int(row['pc'],16)
        if pc in probes:
            c=probes[pc];assert pc not in seen and int(row['instruction'],16)==c['word']
            assert (row['trap']=='1')==bool(c['cause'])
            assert row['rd_write']==str(int(not c['cause']))
            if c['cause']:
                assert int(row['cause'])==c['cause'] and int(row['tval'],16)==c['address']
                assert int(rows[n+1]['pc'],16)==labels['m_trap'];faults+=1
            else:
                assert row['rd']=='7' and row['rd_fp']=='0' and int(row['wdata'],16)==c['result'];results+=1
                assert int(rows[n+1]['pc'],16)==labels[f'after_{c["id"]}']
            seen.add(pc)
        if pc in reads:
            assert pc not in observed and row['trap']=='0' and row['rd_write']=='1' and row['rd']=='10'
            assert int(row['wdata'],16)==reads[pc],row
            observed.add(pc)
    assert seen==set(probes) and observed==set(reads)
    traps=[row for row in rows if row['trap']=='1' and int(row['pc'],16)>=0x80000000]
    assert len(traps)==len(plan)+faults
    return dict(cases=len(seen),faults=faults,results=results,observed_values=len(observed),traps=len(traps))


def verifier(mode,folder):
    def verify(sail,rtl):
        rows=read_csv(rtl);events,mismatch=compare(read_csv(sail),rows);assert mismatch is None,mismatch
        nm=subprocess.check_output([str(GCC/'riscv-none-elf-nm.exe'),'-n',str(folder/'test.elf')],text=True)
        labels={p[2]:int(p[0],16) for line in nm.splitlines() if len(p:=line.split())==3}
        plan=cases(mode);result=inspect(rows,plan,labels);controls=[]
        for kind in ('cause','tval','fault_write','result','guard'):
            broken=copy.deepcopy(rows)
            if kind in ('cause','tval','fault_write'):
                case=next(c for c in plan if c['cause']);pc=labels[f'probe_{case["id"]}']
            elif kind=='result':pc=labels[f'probe_{next(c for c in plan if not c["cause"])["id"]}']
            else:pc=labels['guard_1']
            row=next(r for r in broken if int(r['pc'],16)==pc)
            if kind=='cause':row['cause']='2'
            elif kind=='tval':row['tval']=f'{int(row["tval"],16)^1:016x}'
            elif kind=='fault_write':row['rd_write']='1'
            else:row['wdata']=f'{int(row["wdata"],16)^1:016x}'
            try:inspect(broken,plan,labels)
            except AssertionError:controls.append(kind)
            else:raise AssertionError('Bad atomic fault witness accepted')
        return dict(**result,matched_events=events,rejected_mutations=controls)
    return verify


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    FOLDER.mkdir(parents=True,exist_ok=True)
    top=dict(passed=False,complete_profile_validation=False,generator_sha256=sha(__file__),cases=[])
    if args.check:
        saved=json.loads((FOLDER/'report.json').read_bytes());assert saved['passed'] and saved['generator_sha256']==sha(__file__)
        assert len(saved['cases'])==3
    for index,mode in enumerate(MODES):
        folder=FOLDER/mode;folder.mkdir(exist_ok=True);source=folder/'test.S';verify=verifier(mode,folder)
        if args.check:
            result=check_fixture(folder,__file__,fixture(mode),verify)
            assert saved['cases'][index]==dict(mode=mode,outcomes=result,report_sha256=sha(folder/'report.json'))
        else:
            source.write_text(fixture(mode),encoding='utf-8')
            result=run_fixture(source,folder,__file__,verify,source_dependencies=['scripts/audit_hv_sail_fixture.py'],timeout_cycles=4000000)
        top['cases'].append(dict(mode=mode,outcomes=result,report_sha256=sha(folder/'report.json')))
        if not args.check:dump(FOLDER/'report.json',top)
        print('PASS atomic faults',mode,result,flush=True)
    if not args.check:top['passed']=True;dump(FOLDER/'report.json',top)


if __name__=='__main__':main()

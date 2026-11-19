"""Sv39 and two-stage LR/SC/AMO fault priority with precise guest metadata."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from run_atomic_fault_contract import INITIAL, OPERAND, memory_value, inspect
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha

FOLDER=ROOT/'out/rva23/atomic_translation_faults'
MODES=('HS','U','VS','VU')
DEPENDENCIES=['scripts/audit_hv_sail_fixture.py','scripts/run_atomic_fault_contract.py']
CONTEXTS=('rw','invalid','ro','a0','d0','wrong_u','pmp','invalid_pmp',
          'g_bad','implicit','g_a0','g_d0','g_ro','both_bad')


def cases(mode):
    virtual=mode in ('VS','VU');user=mode in ('U','VU');plan=[]
    for shape in range(3):
        for op in (2,3,0):
            for context in CONTEXTS:
                for bad in (0,1):
                    sf={'invalid':0,'invalid_pmp':0,'both_bad':0,'ro':0x43,'a0':0x87,'d0':0x47}.get(context,0xc7)
                    sf|=int(not user if context=='wrong_u' else user)<<4
                    gf={'g_bad':0,'both_bad':0,'g_a0':0x9f,'g_d0':0x5f,'g_ro':0xd3}.get(context,0xdf)
                    cause=0;guest=0;implicit=0
                    if bad:cause=4 if op==2 else 6
                    elif context=='implicit':
                        cause=(21 if op==2 else 23) if virtual else (5 if op==2 else 7)
                        if virtual:guest=0x10000000;implicit=1
                    elif context in ('invalid','invalid_pmp','both_bad','a0','wrong_u') or (context in ('ro','d0') and op!=2):cause=13 if op==2 else 15
                    elif virtual and (context in ('g_bad','g_a0') or (context in ('g_d0','g_ro') and op!=2)):
                        cause=21 if op==2 else 23;guest=0x200a0000+(4 if shape==2 else 0)
                    elif context=='pmp':cause=5 if op==2 else 7
                    result,memory=memory_value(op,shape)
                    if cause:result,memory=0x55aa,INITIAL
                    plan.append(dict(id=len(plan)+1,shape=shape,op=op,context=context,bad=bad,sf=sf,gf=gf,
                        address=0x400a0000+(4 if shape==2 else 0)+bad,cause=cause,result=result,memory=memory,
                        guest=guest,implicit=implicit,gva=int(virtual),
                        word=op<<27 | (0 if op==2 else 9)<<20 | 8<<15 | (2 if shape else 3)<<12 | 7<<7 | 0x2f))
    assert len(plan)==252
    return plan


def fixture(mode):
    virtual=mode in ('VS','VU');user=mode in ('U','VU');priv=0 if user else 1
    lines=['.section .text.init,"ax"','.option norvc','.globl _start','_start:',
        'la t0,m_trap','csrw mtvec,t0','csrw medeleg,zero','csrw mie,zero',
        'li t0,0x800a0000','srli t0,t0,2','csrw pmpaddr0,t0','li t0,-1','csrw pmpaddr1,t0',
        'csrw menvcfg,zero','csrw henvcfg,zero','csrw hstatus,zero']
    for c in cases(mode):
        i=c['id']
        lines += [f'setup_{i}:',f'li s4,{i}',f'li s2,{c["cause"]}',f'la s3,probe_{i}',f'la s5,after_{i}',f'la s6,capture_{i}',
            'li s7,0',f'li s8,{c["guest"]>>2}',f'li s9,{0x3000 if c["implicit"] else 0}',
            f'li s11,{10 if mode=="VS" else 8 if user else 9}',f'li a1,{int(virtual)}',f'li a2,{priv}',f'li a3,{int(virtual)}',
            f'li t0,{0x1f00|0x18|(0 if c["context"] in ("pmp","invalid_pmp") else 7)}','csrw pmpcfg0,t0',
            'li s10,0x800a0000',f'li t0,{INITIAL:#x}','sd t0,0(s10)',
            'li t0,0x800a0040','sc.d zero,zero,(t0)',
            'la t0,root',f'li t1,{0x200000cf|(16 if user else 0):#x}','sd t1,16(t0)']
        if c['context']=='implicit':lines += [f'li t1,{(0x10000000 if virtual else 0x90000000)>>2|1:#x}']
        else:lines += ['la t1,level1','srli t1,t1,2','ori t1,t1,1']
        lines += ['sd t1,8(t0)','la t0,level1',f'li t1,{(0x08000000 if virtual else 0x20000000)|c["sf"]:#x}','sd t1,0(t0)',
            'la t0,groot','la t1,glevel1','srli t1,t1,2','ori t1,t1,1','sd t1,0(t0)',
            'li t1,0x200000df','sd t1,16(t0)','la t0,glevel1','sd zero,1024(t0)',
            f'li t1,{0x20000000|c["gf"] if c["gf"] else 0:#x}','li t3,2048','add t0,t0,t3','sd t1,0(t0)',
            'la t0,root','srli t0,t0,12','li t1,0x8000000000000000','or t0,t0,t1',
            f'csrw {"vsatp" if virtual else "satp"},t0']
        if virtual:lines += ['csrw satp,zero','la t0,groot','srli t0,t0,12','or t0,t0,t1','csrw hgatp,t0']
        else:lines += ['csrw vsatp,zero','csrw hgatp,zero']
        lines += ['sfence.vma','hfence.gvma','hfence.vvma',f'li s0,{c["address"]:#x}',f'li s1,{OPERAND:#x}',
            'li t2,0x55aa',f'li t0,{priv<<11|int(virtual)<<39}','csrw mstatus,t0',
            f'la t0,probe_{i}','csrw mepc,t0','mret',f'probe_{i}:.word {c["word"]:#x}',f'after_{i}:ecall','j fail',
            f'capture_{i}:',f'value_{i}:mv a0,t2',f'li t3,{c["result"]:#x}','bne a0,t3,fail',
            f'guard_{i}:ld a0,0(s10)',f'li t3,{c["memory"]:#x}','bne a0,t3,fail']
    lines += ['li t1,1','j finish','m_trap:','csrr t0,mcause','beq t0,s11,case_done','beqz s2,fail',
        'bne t0,s2,fail','bnez s7,fail','csrr t0,mepc','bne t0,s3,fail','csrr t0,mtval','bne t0,s0,fail',
        'csrr t0,mtval2','bne t0,s8,fail','csrr t0,mtinst','bne t0,s9,fail',
        'csrr t0,mstatus','srli t1,t0,38','andi t1,t1,1','bne t1,a3,fail',
        'srli t1,t0,39','andi t1,t1,1','bne t1,a1,fail','srli t1,t0,11','andi t1,t1,3','bne t1,a2,fail',
        'li s7,1','csrw mepc,s5','mret','case_done:','csrr t0,mepc','bne t0,s5,fail','snez t0,s2','bne t0,s7,fail','jr s6',
        'fail:slli t1,s4,1','ori t1,t1,1','finish:la t0,tohost','sd t1,0(t0)','halt:j halt',
        '.section .tohost,"aw"','.balign 8','.globl tohost,fromhost','tohost:.dword 0','fromhost:.dword 0',
        '.section .bss,"aw",@nobits','.balign 4096','root:.space 4096','level1:.space 4096',
        '.balign 16384','groot:.space 16384','glevel1:.space 4096']
    return '\n'.join(lines)+'\n'


def inspect_metadata(rows,plan,labels,mode):
    virtual=mode in ('VS','VU');priv=0 if mode in ('U','VU') else 1;count=0
    for c in plan:
        if not c['cause']:continue
        n=next(n for n,r in enumerate(rows) if int(r['pc'],16)==labels[f'probe_{c["id"]}'])
        reads={}
        for r in rows[n+1:]:
            word=int(r['instruction'],16)
            if word==0x30200073:break
            if word&0x707f==0x2073 and r['rd_write']=='1':reads[word>>20]=int(r['wdata'],16)
        assert reads[0x34b]==c['guest']>>2 and reads[0x34a]==(0x3000 if c['implicit'] else 0)
        assert (reads[0x300]>>38&1,reads[0x300]>>39&1,reads[0x300]>>11&3)==(int(virtual),int(virtual),priv)
        count+=1
    return count


def verifier(mode,folder):
    def verify(sail,rtl):
        rows=read_csv(rtl);events,mismatch=compare(read_csv(sail),rows);assert mismatch is None,mismatch
        nm=subprocess.check_output([str(GCC/'riscv-none-elf-nm.exe'),'-n',str(folder/'test.elf')],text=True)
        labels={p[2]:int(p[0],16) for line in nm.splitlines() if len(p:=line.split())==3}
        plan=cases(mode);result=inspect(rows,plan,labels);metadata=inspect_metadata(rows,plan,labels,mode);controls=[]
        for kind in ('cause','tval','result','guard','guest_address','implicit','gva'):
            broken=copy.deepcopy(rows)
            c=next(c for c in plan if c['cause'])
            if kind=='result':c=next(c for c in plan if not c['cause'])
            pc=labels['guard_1'] if kind=='guard' else labels[f'probe_{c["id"]}']
            n=next(n for n,r in enumerate(broken) if int(r['pc'],16)==pc);row=broken[n]
            if kind=='cause':row['cause']='2'
            elif kind=='tval':row['tval']=f'{int(row["tval"],16)^1:016x}'
            elif kind in ('guest_address','implicit','gva'):
                csr={'guest_address':0x34b,'implicit':0x34a,'gva':0x300}[kind]
                row=next(r for r in broken[n+1:] if int(r['instruction'],16)>>20==csr and r['rd_write']=='1')
                row['wdata']=f'{int(row["wdata"],16)^(1<<38 if kind=="gva" else 1):016x}'
            else:row['wdata']=f'{int(row["wdata"],16)^1:016x}'
            try:inspect(broken,plan,labels);inspect_metadata(broken,plan,labels,mode)
            except AssertionError:controls.append(kind)
            else:raise AssertionError('Bad translated atomic witness accepted')
        return dict(**result,metadata_faults=metadata,matched_events=events,rejected_mutations=controls)
    return verify


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    FOLDER.mkdir(parents=True,exist_ok=True)
    top=dict(passed=False,complete_profile_validation=False,generator_sha256=sha(__file__),cases=[])
    if args.check:
        saved=json.loads((FOLDER/'report.json').read_bytes());assert saved['passed'] and saved['generator_sha256']==sha(__file__)
        assert len(saved['cases'])==len(MODES)
    for index,mode in enumerate(MODES):
        folder=FOLDER/mode;folder.mkdir(exist_ok=True);source=folder/'test.S';verify=verifier(mode,folder)
        if args.check:
            result=check_fixture(folder,__file__,fixture(mode),verify)
            assert saved['cases'][index]==dict(mode=mode,outcomes=result,report_sha256=sha(folder/'report.json'))
        else:
            source.write_text(fixture(mode),encoding='utf-8')
            result=run_fixture(source,folder,__file__,verify,source_dependencies=DEPENDENCIES,timeout_cycles=5000000)
        top['cases'].append(dict(mode=mode,outcomes=result,report_sha256=sha(folder/'report.json')))
        if not args.check:dump(FOLDER/'report.json',top)
        print('PASS translated atomic faults',mode,result,flush=True)
    if not args.check:top['passed']=True;dump(FOLDER/'report.json',top)


if __name__=='__main__':main()

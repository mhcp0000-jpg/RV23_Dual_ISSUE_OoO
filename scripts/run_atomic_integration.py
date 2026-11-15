"""Execute A instructions in the actual OoO core, cache and main AXI SRAM."""
import csv,json,random
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/atomic';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/scalar/model.json').read_text())
assert '-GHAS_A=1' in model['params']
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
mask=(1<<64)-1
def signed(v,bits):return v-(1<<bits) if v>>(bits-1) else v
ops=['add','swap','xor','or','and','min','max','minu','maxu']
def oracle(op,a,b,bits):
    m=(1<<bits)-1;a&=m;b&=m
    return {'add':lambda:a+b,'swap':lambda:b,'xor':lambda:a^b,
        'or':lambda:a|b,'and':lambda:a&b,
        'min':lambda:min(signed(a,bits),signed(b,bits)),
        'max':lambda:max(signed(a,bits),signed(b,bits)),
        'minu':lambda:min(a,b),'maxu':lambda:max(a,b)}[op]()&m
lines=['.section .text.init,"ax"','.option norvc','.globl _start','_start:',
    'la t0,m_trap','csrw mtvec,t0','li s0,0x80070000','li s6,0',
    'csrr t0,misa','andi t0,t0,1','beqz t0,fail']
rng=random.Random(0xA2364);cases=0
values=[0,1,mask,1<<63,0x7fffffffffffffff,0x80000000,0x7fffffff]
for word,lane in [(False,0),(True,0),(True,1)]:
    bits=32 if word else 64
    for op in ops:
        for v in range(9):
            a=values[v] if v<len(values) else rng.getrandbits(64)
            b=values[-1-v] if v<len(values) else rng.getrandbits(64)
            initial=a if not word else ((a&0xffffffff)<<(32*lane))|(0xa55a1234<<(32*(1-lane)))
            old=(signed(a&0xffffffff,32)&mask) if word else a
            result=oracle(op,a,b,bits)
            expected=result if not word else (initial&~(0xffffffff<<(32*lane)))|(result<<(32*lane))
            suffix='w' if word else 'd'
            lines += [f'li t0,0x{initial:016x}','sd t0,0(s0)',
                'ld t1,0(s0)', 'bne t0,t1,fail', # populate D-cache before bypass AMO
                f'li t2,0x{b:016x}',f'addi s1,s0,{4*lane}',
                f'amo{op}.{suffix}.aqrl t3,t2,(s1)',
                f'li t4,0x{old:016x}','bne t3,t4,fail',
                'ld t3,0(s0)',f'li t4,0x{expected:016x}','bne t3,t4,fail']
            cases+=1
lines += ['li t0,0','sd t0,0(s0)','li s2,100','lr_loop:',
    'lr.d.aq t1,(s0)','addi t1,t1,1','sc.d.rl t2,t1,(s0)',
    'bnez t2,lr_loop','addi s2,s2,-1','bnez s2,lr_loop',
    'ld t1,0(s0)','li t2,100','bne t1,t2,fail',
    'sc.d t2,zero,(s0)','li t3,1','bne t2,t3,fail',
    'lr.d t1,(s0)','li t2,7','sd t2,0(s0)', # same-hart store snoop
    'sc.d t2,zero,(s0)','li t3,1','bne t2,t3,fail',
    'lr.d t1,(s0)','addi s1,s0,8','sc.d t2,zero,(s1)',
    'li t3,1','bne t2,t3,fail','sc.d t2,zero,(s0)','bne t2,t3,fail',
    'lr.w t1,(s0)','sc.d t2,zero,(s0)','bne t2,t3,fail']
# Precise faults, including a faulting SC that must consume the old LR.
for insn,addr,cause in [('lr.d t1,(s1)',0x80070002,4),
    ('sc.d t1,zero,(s1)',0x80070002,6),('amoadd.d t1,zero,(s1)',0x02000000,7),
    ('lr.d t1,(s1)',0x02000000,5)]:
    lines += ['lr.d t1,(s0)',f'li s1,0x{addr:x}',f'li a4,{cause}',
        'mv a5,s1',insn,'sc.d t1,zero,(s0)','li t2,1','bne t1,t2,fail']
lines += ['li t0,4','bne s6,t0,fail','lui t0,0x10000','li t1,0x41544f4d',
    'sw t1,0xc(t0)','sw zero,0x14(t0)','1:wfi','j 1b',
    'm_trap:','csrr t4,mcause','bne t4,a4,fail','csrr t4,mtval',
    'bne t4,a5,fail','addi s6,s6,1','csrr t4,mepc','addi t4,t4,4',
    'csrw mepc,t4','mret','fail:','lui t0,0x10000','li t1,1','sw t1,0x14(t0)','j 1b']
source=folder/'test.S';source.write_text('\n'.join(lines)+'\n',encoding='utf-8')
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imafc_zicsr_zifencei','-mabi=lp64f',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=2000000','+expected_exit_code=0'],folder/'simulation.log',180)
    fresh();assert 'PASS rv32_program_tb' in text and 'data=0x41544f4d' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert [int(r['cause']) for r in traps]==[4,6,7,5],traps
    atomics=[r for r in rows if int(r['instruction'],16)&0x7f==0x2f and r['trap']=='0']
    assert len(atomics)>=cases+200
    report={'passed':True,'scope':'Integrated RV64 A W/D, LR/SC progress and precise faults; virtual atomic tests tracked separately',
        'model_inputs':model['inputs'],'binary':model['binary'],'binary_sha256':model['binary_sha256'],
        'elf':elf.relative_to(ROOT).as_posix(),'elf_sha256':sha(elf),'source_sha256':sha(source),
        'generator_sha256':sha(__file__),'run':run,'trace_sha256':sha(trace),
        'amo_oracle_cases':cases,'atomic_retirements':len(atomics),
        'traps':[{k:r[k] for k in ['pc','instruction','cause','tval']} for r in traps]}
    dump(folder/'report.json',report)
    print('PASS RV64 A integrated oracle cases',cases,'atomic retirements',len(atomics),flush=True)

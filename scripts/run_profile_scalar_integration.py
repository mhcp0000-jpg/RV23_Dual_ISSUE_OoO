"""Actual retirement/semantics for Zimop, Zcmop, Zcb, Zawrs and Svinval."""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/profile_scalar';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/scalar/model.json').read_text())
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
lines=['.section .text.init,"ax"','.option norvc','.globl _start','_start:',
       'la t0,fail','csrw mtvec,t0']
for n in range(32):
    for rd in ['t3','t4','zero']:
        lines += [f'li {rd},-1','li t0,0x12345678',f'mop.r.{n} {rd},t0',f'bnez {rd},fail']
for n in range(8):
    for rd in ['t3','t4','zero']:
        lines += [f'li {rd},-1','li t1,0xdeadbeef',f'mop.rr.{n} {rd},t0,t1',f'bnez {rd},fail']
for n in range(1,16,2):
    lines += [f'li x{n},0x1357','.option push','.option arch,+zca,+zcmop',f'c.mop.{n}',
              '.option pop','li t6,0x1357',f'bne x{n},t6,fail']
def compressed(insn):return ['.option push','.option arch,+zca,+zcb,+zcmop',insn,'.option pop']
for value in [0,0xffffffffffffffff,0x11223344800080ff,0x8877665501234567]:
    for op,expected in [('zext.b',value&255),('sext.b',((value&255)^128)-128),
        ('zext.h',value&65535),('sext.h',((value&65535)^32768)-32768),
        ('zext.w',value&0xffffffff),('not',value^0xffffffffffffffff)]:
        lines += [f'li s1,0x{value:016x}',*compressed(f'c.{op} s1'),
                  f'li t0,0x{expected&0xffffffffffffffff:016x}','bne s1,t0,fail']
lines += ['li s1,-123','li a0,45',*compressed('c.mul s1,a0'),'li t0,-5535','bne s1,t0,fail']
for offset in range(4):
    lines += ['li s0,0x80070000','li t0,-1','sd t0,0(s0)','li s1,0x80',
              *compressed(f'c.sb s1,{offset}(s0)'),*compressed(f'c.lbu a0,{offset}(s0)'),
              'li t0,0x80','bne a0,t0,fail','ld t0,0(s0)',
              f'li t1,0x{(0xffffffffffffffff & ~(255<<(offset*8)))|(128<<(offset*8)):016x}',
              'bne t0,t1,fail']
for offset in [0,2]:
    lines += ['li s0,0x80070000','li t0,-1','sd t0,0(s0)','li s1,0x80ff',
              *compressed(f'c.sh s1,{offset}(s0)'),*compressed(f'c.lhu a0,{offset}(s0)'),
              'li t0,0x80ff','bne a0,t0,fail',*compressed(f'c.lh a0,{offset}(s0)'),
              'li t0,-32513','bne a0,t0,fail']
lines += ['lui t0,0x10000','li t1,0x50534331','sw t1,0xc(t0)','sw zero,0x14(t0)',
          '1:wfi','j 1b','fail:','lui t0,0x10000','li t1,1','sw t1,0x14(t0)','j 1b']
source=folder/'instructions.S';source.write_text('\n'.join(lines)+'\n',encoding='utf-8')
with Simulator() as sim:
    results=[]
    for label,source,signature,expected_causes in [
        ('instructions',source,'50534331',[]),
        ('wait',ROOT/'sw/tests/rv64_profile_wait.S','57525331',[2,2,2,2,2])]:
        elf=folder/(label+'.elf');trace=folder/(label+'_commit.csv')
        sim.run([GCC/'riscv-none-elf-gcc.exe',
            '-march=rv64imafc_zba_zbb_zcb_zcmop_zimop_zawrs_svinval_zicsr_zifencei','-mabi=lp64f',
            '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
            '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/(label+'_compile.log'),60)
        run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
            '+timeout_cycles=2000000','+expected_exit_code=0'],folder/(label+'_simulation.log'),180)
        fresh();assert 'PASS rv32_program_tb' in text and f'data=0x{signature}' in text
        with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
        traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
        assert [int(r['cause']) for r in traps]==expected_causes,traps
        results.append({'label':label,'passed':True,'source_sha256':sha(source),
            'elf_sha256':sha(elf),'trace_sha256':sha(trace),'run':run,'traps':traps})
        print('PASS RV64 profile scalar integrated',label,flush=True)
    dump(folder/'report.json',{'passed':True,'model_inputs':model['inputs'],
        'binary_sha256':model['binary_sha256'],'cases':results})

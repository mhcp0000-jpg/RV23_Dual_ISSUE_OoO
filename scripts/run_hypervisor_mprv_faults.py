"""Native MPRV+MPV explicit/implicit guest faults and actual-mode trap state."""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump,source_inputs

folder=ROOT/'out/rva23/hypervisor_mprv_faults';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
assert '-GHAS_H=1' in model['params'] and '-GXLEN=64' in model['params']
files=(ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv','tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
inputs=source_inputs(files);assert inputs==model['inputs']
runtime={p:sha(ROOT/p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex','sw/benchmarks/coremark/rv32_tim.ld']}
def fresh():
    for p,h in {**inputs,**runtime}.items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh();cases=[]
for privilege in [0,1]:
    for implicit in [False,True]:
        for write in [False,True]:
            cases.append(dict(id=len(cases)+1,privilege=privilege,implicit=implicit,write=write,
                              address=0x400a0000 if implicit else 0x20000000,
                              cause=23 if write else 21,gva=1,
                              guest_address=0x10000008 if implicit else 0x20000000))
for write in [False,True]:cases.append(dict(id=len(cases)+1,privilege=3,implicit=False,write=write,
                                          address=0x90000000,cause=7 if write else 5,gva=0,guest_address=0))
lines=['.section .text.init,"ax"','.option norvc','.globl _start','_start:',
       '  lui t0,0x02000','  sw zero,0(t0)','  la t0,m_trap','  csrw mtvec,t0',
       '  la t0,fail','  csrw stvec,t0','  li t0,-1','  csrw pmpaddr0,t0','  li t0,31','  csrw pmpcfg0,t0',
       '  li t0,-1','  csrw medeleg,t0', # actual M faults must stay M despite delegation
       '  la t0,groot','  srli t0,t0,12','  li t1,0x8000000000000000','  or t0,t0,t1','  csrw hgatp,t0',
       '  li a0,0']
for c in cases:
    n=c['id'];status=(1<<38) if c['privilege']==3 else ((1<<39)|(1<<38)|(1<<17)|(c['privilege']<<11))
    lines += [f'  li s0,{n}',f'  li s1,{c["cause"]}',f'  li s2,{c["address"]}',
              f'  li s3,{c["guest_address"]>>2}',f'  li s4,{0x3000 if c["implicit"] else 0}',
              f'  li s5,{c["gva"]}',f'  la s6,probe_{n}',f'  la s7,resume_{n}',
              f'  li t0,{0x8000000000010000 if c["implicit"] else 0}','  csrw vsatp,t0',
              f'  li t0,{status}','  csrw mstatus,t0',f'  li t3,{c["address"]}',
              '  li t4,0x12345678',f'probe_{n}:',
              '  sd t4,0(t3)' if c['write'] else '  ld t4,0(t3)',
              '  j fail',f'resume_{n}:']
lines += [f'  li t0,{len(cases)}','  bne a0,t0,fail','  lui t0,0x10000','  li t1,0x4d505246',
          '  sw t1,0xc(t0)','  sw zero,0x14(t0)','1:j 1b',
          '.balign 4','m_trap:','  csrr t0,mcause','  bne t0,s1,fail','  csrr t0,mtval','  bne t0,s2,fail',
          '  csrr t0,mtval2','  bne t0,s3,fail','  csrr t0,mtinst','  bne t0,s4,fail',
          '  csrr t0,mepc','  bne t0,s6,fail','  csrr t0,mstatus',
          '  srli t1,t0,38','  andi t1,t1,1','  bne t1,s5,fail',
          '  srli t1,t0,39','  andi t1,t1,1','  bnez t1,fail', # MPV saves actual V=0, not effective MPV
          '  srli t1,t0,11','  andi t1,t1,3','  li t2,3','  bne t1,t2,fail',
          '  li t0,0x8000020000','  csrc mstatus,t0','  addi a0,a0,1','  csrw mepc,s7','  mret',
          'fail:','  lui t0,0x10000','  sw s0,0xc(t0)','  li t1,1','  sw t1,0x14(t0)','  j 1b',
          '.section .bss,"aw",@nobits','.balign 16384','groot:.skip 16384']
source=folder/'test.S';source.write_text('\n'.join(lines)+'\n',encoding='utf-8');dump(folder/'cases.json',cases)
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    compile_record,_=sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh','-mabi=lp64d',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=300000','+expected_exit_code=0'],folder/'simulation.log',120)
    fresh();assert 'PASS rv32_program_tb' in text and 'data=0x4d505246' in text
    with trace.open(newline='') as stream:
        traps=[row for row in csv.DictReader(stream) if row['trap']=='1' and int(row['pc'],16)>=0x80000000]
    assert [int(row['cause']) for row in traps]==[c['cause'] for c in cases]
    assert [int(row['tval'],16) for row in traps]==[c['address'] for c in cases]
    dump(folder/'report.json',dict(passed=True,scope='MPRV+MPV actual-M explicit and implicit-PTE guest faults with both effective VS/VU privileges, GVA/MPV/MPP and mtval2/mtinst; ordinary M controls',
        model=model,runtime_inputs=runtime,generator_sha256=sha(__file__),source_sha256=sha(source),
        cases_sha256=sha(folder/'cases.json'),elf_sha256=sha(elf),trace_sha256=sha(trace),
        compile=compile_record,run=run,case_count=len(cases),traps=traps))
print('PASS MPRV+MPV fault metadata: 8 guest faults plus 2 ordinary-M controls',flush=True)

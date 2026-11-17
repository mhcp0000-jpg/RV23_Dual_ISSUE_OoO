"""Native breakpoint/illegal trap-value and GVA/delegation/return matrix."""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump,source_inputs

folder=ROOT/'out/rva23/hypervisor_breakpoint_metadata';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
assert '-GHAS_H=1' in model['params'] and '-GXLEN=64' in model['params']
files=(ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv','tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
inputs=source_inputs(files);assert model['inputs']==inputs
runtime={p:sha(ROOT/p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex','sw/benchmarks/coremark/rv32_tim.ld']}
def fresh():
    for p,h in {**inputs,**runtime}.items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
contexts=[('VS','HS'),('VU','HS'),('VS','M'),('VU','M'),('M','M'),('HS','M'),('U','M'),
          ('HS','HS'),('U','HS'),('VS','VS'),('VU','VS')]
forms=[('ebreak',0x100073,4,3),('c.ebreak',0x9002,2,3),('illegal',0xffffffff,4,2),
       ('reserved_c.addi4spn',0x0004,2,2),
       ('fs_off_c.fld',0x2404,2,2),('fs_off_c.fsd',0xa000,2,2),
       ('fs_off_c.fldsp',0x2002,2,2),('fs_off_c.fsdsp',0xa01a,2,2)]
cases=[]
for mode,target in contexts:
    for name,opcode,length,cause in forms:
        cases.append(dict(id=len(cases)+1,mode=mode,target=target,name=name,opcode=opcode,length=length,cause=cause))
lines=['.section .text.init,"ax"','.option norvc','.globl _start','_start:',
       '  lui t0,0x02000','  sw zero,0(t0)','  li t0,-1','  csrw pmpaddr0,t0',
       '  li t0,31','  csrw pmpcfg0,t0','  li a0,0','  j setup_1']
for case in cases:
    n=case['id'];mode=case['mode'];target=case['target'];virtual=mode in ['VS','VU']
    priv=3 if mode=='M' else 1 if mode in ['HS','VS'] else 0
    status=(priv<<11)|(int(virtual)<<39)|(1<<38) # seed old GVA=1; trap must replace it
    # Test the guest FS gate independently of the host FS gate.
    if virtual and case['name'].startswith('fs_off_'):
        status |= 1<<13
    lines += [f'setup_{n}:',f'  li s0,{n}',f'  li s1,{case["cause"]}',
              f'  la s3,probe_{n}',f'  la s4,after_{n}',f'  la s11,after_{n}',
              f'  la s5,{"finish" if n==len(cases) else "setup_"+str(n+1)}',
              f'  li s6,{["M","HS","VS"].index(target)}',
              f'  li s7,{int(virtual and case["cause"]==3)}',f'  li s8,{priv}',f'  li s9,{int(virtual)}',
              f'  li s10,{11 if mode=="M" else 10 if mode=="VS" else 9 if mode=="HS" else 8}',
              '  li a1,0','  la t0,m_trap','  csrw mtvec,t0','  la t0,hs_trap','  csrw stvec,t0',
              '  la t0,vs_trap','  csrw vstvec,t0',
              f'  li t0,{0 if target=="M" else 1<<case["cause"]}','  csrw medeleg,t0',
              f'  li t0,{1<<case["cause"] if target=="VS" else 0}','  csrw hedeleg,t0',
              '  li t0,0x140','  csrw hstatus,t0','  csrw vsstatus,zero',
              f'  li t0,{status}','  csrw mstatus,t0']
    if case['cause']==3:lines.append('  mv s2,s3')
    else:lines.append(f'  li s2,{case["opcode"]:#x}')
    if mode=='M':lines.append(f'  j probe_{n}')
    else:lines += [f'  la t0,probe_{n}','  csrw mepc,t0','  mret']
    lines += [f'probe_{n}:',f'  {".hword" if case["length"]==2 else ".word"} {case["opcode"]}',
              f'after_{n}:','  ecall','  j fail']
lines += ['.balign 4','m_trap:','  csrr t0,mcause','  beq t0,s10,case_done','  bnez s6,fail','  bne t0,s1,fail',
          '  csrr t0,mtval','  bne t0,s2,fail','  csrr t0,mepc','  bne t0,s3,fail',
          '  csrr t0,mstatus','  srli t1,t0,38','  andi t1,t1,1','  bne t1,s7,fail',
          '  srli t1,t0,39','  andi t1,t1,1','  bne t1,s9,fail',
          '  srli t1,t0,11','  andi t1,t1,3','  bne t1,s8,fail',
          '  csrr t0,mtval2','  bnez t0,fail','  csrr t0,mtinst','  bnez t0,fail',
          '  addi a1,a1,1','  csrw mepc,s4','  mret',
          '.balign 4','hs_trap:','  li t0,1','  bne s6,t0,fail','  csrr t0,scause','  bne t0,s1,fail',
          '  csrr t0,stval','  bne t0,s2,fail','  csrr t0,sepc','  bne t0,s3,fail',
          '  csrr t0,hstatus','  srli t1,t0,6','  andi t1,t1,1','  bne t1,s7,fail',
          '  srli t1,t0,7','  andi t1,t1,1','  bne t1,s9,fail',
          '  srli t1,t0,8','  andi t1,t1,1','  li t2,1','  beqz s9,1f','  mv t2,s8','1: bne t1,t2,fail',
          '  csrr t0,sstatus','  srli t0,t0,8','  andi t0,t0,1','  bne t0,s8,fail',
          '  csrr t0,htval','  bnez t0,fail','  csrr t0,htinst','  bnez t0,fail',
          '  addi a1,a1,1','  csrw sepc,s4','  sret',
          '.balign 4','vs_trap:','  li t0,2','  bne s6,t0,fail','  csrr t0,scause','  bne t0,s1,fail',
          '  csrr t0,stval','  bne t0,s2,fail','  csrr t0,sepc','  bne t0,s3,fail',
          '  csrr t0,sstatus','  srli t0,t0,8','  andi t0,t0,1','  bne t0,s8,fail',
          '  addi a1,a1,1','  csrw sepc,s4','  sret',
          'case_done:','  csrr t0,mepc','  bne t0,s11,fail','  li t0,1','  bne a1,t0,fail',
          '  csrr t0,mstatus','  srli t0,t0,38','  andi t0,t0,1','  bnez t0,fail',
          '  csrr t0,hstatus','  srli t0,t0,6','  andi t0,t0,1','  li t1,1','  li t2,1',
          '  bne s6,t2,2f','  mv t1,s7','2: bne t0,t1,fail',
          '  addi a0,a0,1','  csrw mstatus,zero','  jr s5',
          'finish:',f'  li t0,{len(cases)}','  bne a0,t0,fail',
          '  lui t0,0x10000','  li t1,0x42504d31','  sw t1,0xc(t0)','  sw zero,0x14(t0)','3:j 3b',
          'fail:','  lui t0,0x10000','  sw s0,0xc(t0)','  li t1,1','  sw t1,0x14(t0)','  j 3b']
source=folder/'test.S';source.write_text('\n'.join(lines)+'\n',encoding='utf-8');dump(folder/'cases.json',cases)
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    compile_record,_=sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh','-mabi=lp64d',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=200000','+expected_exit_code=0'],folder/'simulation.log',120)
    fresh();assert 'PASS rv32_program_tb' in text and 'data=0x42504d31' in text
    with trace.open(newline='') as stream:
        traps=[row for row in csv.DictReader(stream) if row['trap']=='1' and int(row['pc'],16)>=0x80000000]
    expected=[value for case in cases for value in [case['cause'],11 if case['mode']=='M' else 10 if case['mode']=='VS' else 9 if case['mode']=='HS' else 8]]
    assert [int(row['cause']) for row in traps]==expected
    for case,row in zip(cases,traps[::2],strict=True):
        expected_tval=int(row['pc'],16) if case['cause']==3 else case['opcode']
        assert int(row['instruction'],16)==case['opcode'] and int(row['tval'],16)==expected_tval,(case,row)
    dump(folder/'report.json',dict(passed=True,scope='Native M/HS/VS/U/VU EBREAK/C.EBREAK and original 16/32-bit illegal instruction trap values, GVA/MPV/SPV/SPVP, delegation and returns',
        model=model,runtime_inputs=runtime,generator_sha256=sha(__file__),source_sha256=sha(source),
        cases_sha256=sha(folder/'cases.json'),elf_sha256=sha(elf),trace_sha256=sha(trace),
        compile=compile_record,run=run,case_count=len(cases),traps=traps))
print(f'PASS native breakpoint metadata: {len(cases)} contexts/forms and {len(traps)} precise traps',flush=True)

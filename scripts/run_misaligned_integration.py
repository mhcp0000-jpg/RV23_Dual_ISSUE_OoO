"""Full-core misaligned integer/FP load/store and cache/page/bank boundaries."""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/misaligned';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/scalar/model.json').read_text())
assert '-GHAS_MISALIGNED=1' in model['params']
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
memory=bytearray((i*37+128)&255 for i in range(8256));mask=(1<<64)-1;cases=0
code=['''.section .text.init,"ax"
.option norvc
.globl _start
_start:
  lui t0,0x02000
  sw zero,0(t0)
  la t0,m_trap
  csrw mtvec,t0
  li t0,0x6000
  csrw mstatus,t0
  li s6,0
  li s0,0x80070000
  li t0,8256
  li t1,128
fill:
  sb t1,0(s0)
  addi t1,t1,37
  addi s0,s0,1
  addi t0,t0,-1
  bnez t0,fill
''']
def check(value,register='t1'):
    code.extend([f'  li t2,0x{value&mask:016x}',f'  bne {register},t2,fail'])
for boundary in [0,56,4092,8184]:
    for offset in range(1,8):
        for size in [2,4,8]:
            at=boundary+offset
            if at%size==0:continue
            address=0x80070000+at;raw=int.from_bytes(memory[at:at+size],'little')
            code += [f'  li s2,{cases}',f'  li s0,0x{address:016x}']
            op={2:'lh',4:'lw',8:'ld'}[size]
            code += [f'  {op} t1,0(s0)'];check(raw-(1<<(size*8)) if raw>>(size*8-1) else raw)
            if size!=8:code += [f'  {op}u t1,0(s0)'];check(raw)
            code += [f'  f{op} ft0,0(s0)','  fmv.x.d t1,ft0']
            check(raw|((mask>>(size*8))<<(size*8)))
            # Both native integer and FP stores must replay younger readers.
            for floating in [False,True]:
                value=(0x0123456789abcdef^(cases*0x123456789))&mask
                code += [f'  li t0,0x{value:016x}']
                if floating:code += ['  fmv.d.x ft1,t0']
                store={2:'sh',4:'sw',8:'sd'}[size]
                code += [f'  {"f" if floating else ""}{store} {"ft1" if floating else "t0"},0(s0)']
                memory[at:at+size]=(value&((1<<(size*8))-1)).to_bytes(size,'little')
                for aligned in range(at&~7,((at+size-1)&~7)+1,8):
                    code += [f'  li s1,0x{0x80070000+aligned:016x}','  ld t1,0(s1)']
                    check(int.from_bytes(memory[aligned:aligned+8],'little'))
            cases+=1
code += ['''
  li s0,0x8007003f
  li s1,0x1122334455667788
  .option rvc
  c.sd s1,0(s0)
  c.ld a0,0(s0)
  .option norvc
  bne a0,s1,fail
  fmv.d.x fs0,s1
  .option rvc
  c.fsd fs0,0(s0)
  c.fld fs1,0(s0)
  .option norvc
  fmv.x.d t1,fs1
  bne t1,s1,fail
  # Address-only store issue can report alignment before FP data is ready.
  li t0,0x3ff0000000000000
  fmv.d.x ft0,t0
  li t0,0x4000000000000000
  fmv.d.x ft1,t0
  fdiv.d ft2,ft0,ft1
  fsd ft2,0(s0)
  fld ft3,0(s0)
  fmv.x.d t1,ft3
  li t2,0x3fe0000000000000
  bne t1,t2,fail
  ld zero,0(s0)
  # The assist must use the same effective privilege and pointer mask as LSU.
  li t0,-1
  csrw pmpaddr0,t0
  li t0,15
  csrw pmpcfg0,t0
  li t0,2
  slli t0,t0,32
  csrw senvcfg,t0
  li t0,0x26000
  csrw mstatus,t0
  li s0,0xfe0000008007003f
  li t0,0x123456789abcdef0
  sd t0,0(s0)
  ld t1,0(s0)
  bne t1,t0,fail
  fld ft0,0(s0)
  fmv.x.d t1,ft0
  bne t1,t0,fail
  li t0,0x20000
  csrc mstatus,t0
  li s0,0x800ffff8
  li t1,0x1122334455667788
  sd t1,0(s0)
  li s1,0x800ffffd
  li a4,7
  li a5,0x80100000
  sd zero,0(s1)
  ld t1,0(s0)
  li t2,0x1122334455667788
  bne t1,t2,fail
  li s1,0x02000001
  mv a5,s1
  sd zero,0(s1)
  li a4,5
  ld zero,0(s1)
  li t0,3
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x4d495341
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:j 1b
m_trap:
  csrr t4,mcause
  bne t4,a4,fail
  csrr t4,mtval
  bne t4,a5,fail
  addi s6,s6,1
  csrr t4,mepc
  addi t4,t4,4
  csrw mepc,t4
  mret
fail:
  lui t0,0x10000
  li t1,1
  sw t1,0x14(t0)
  j 1b
''']
source=folder/'test.S';source.write_text('\n'.join(code))
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imafdc_zfhmin_zicsr_zifencei','-mabi=lp64d',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=4000000','+expected_exit_code=0'],folder/'simulation.log',240)
    fresh();assert 'PASS rv32_program_tb' in text and 'data=0x4d495341' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert [int(r['cause']) for r in traps]==[7,7,5],traps
    dump(folder/'report.json',{'passed':True,'scope':'Integer/FP misalignment, bank/line/page boundaries, late store data, replay, PMA prevalidation',
        'model_inputs':model['inputs'],'binary_sha256':model['binary_sha256'],
        'cases':cases,'elf_sha256':sha(elf),'source_sha256':sha(source),'generator_sha256':sha(__file__),
        'run':run,'trace_sha256':sha(trace),'traps':traps})
    print('PASS full-core misalignment matrix',cases,'integer/FP cases, cache/bank/page boundaries and PMA faults',flush=True)

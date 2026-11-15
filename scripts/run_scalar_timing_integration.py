"""Same text and control flow, different data fixtures, on the full RV64 SoC.

Compare every measured instruction's relative retirement cycle. This is finite
Zkt-directed evidence, not a formal timing or whole-system security proof.
"""
import csv,json,random
from sim_runner import ROOT,Simulator,GCC,sha,dump

folder=ROOT/'out/rva23/scalar_timing';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text())
assert '-GHAS_H=1' in model['params'] and '-GXLEN=64' in model['params']
for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
assert sha(ROOT/model['binary'])==model['binary_sha256']
runtime_inputs={p:sha(ROOT/p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex','sw/benchmarks/coremark/rv32_tim.ld']}

operations=[]
for name in ['add','sub','slt','sltu','xor','or','and','sll','srl','sra','addw','subw','sllw','srlw','sraw',
             'mul','mulh','mulhsu','mulhu','mulw','sh1add','sh2add','sh3add','andn','orn','xnor',
             'min','minu','max','maxu','rol','ror','rolw','rorw','bclr','bext','binv','bset',
             'add.uw','sh1add.uw','sh2add.uw','sh3add.uw','czero.eqz','czero.nez']:
    operations.extend([f'{name} t2,a0,a1',f'{name} t3,a1,a0','add s0,s0,t2','xor s1,s1,t3'])
for name in ['clz','ctz','cpop','clzw','ctzw','cpopw','sext.b','sext.h','zext.h','orc.b','rev8']:
    operations.extend([f'{name} t2,a0',f'{name} t3,a1','add s0,s0,t2','xor s1,s1,t3'])
for name in ['addi','slti','sltiu','xori','ori','andi','addiw']:
    operations.extend([f'{name} t2,a0,-3',f'{name} t3,a1,7','add s0,s0,t2','xor s1,s1,t3'])
for name in ['slli','srli','srai','slliw','srliw','sraiw','rori','roriw','bclri','bexti','binvi','bseti','slli.uw']:
    operations.extend([f'{name} t2,a0,7',f'{name} t3,a1,31','add s0,s0,t2','xor s1,s1,t3'])
operations+=['lui t2,0x12345','auipc t3,0x12345','add s0,s0,t2','xor s1,s1,t3']
compressed=['c.addi a2,-3','c.addiw a2,1','c.lui a2,0x13','c.srli a2,7','c.srai a2,7',
            'c.andi a2,7','c.sub a2,a3','c.xor a2,a3','c.or a2,a3','c.and a2,a3',
            'c.subw a2,a3','c.addw a2,a3','c.slli a2,7','c.li a2,-3','c.mv a2,a3','c.add a2,a3',
            'c.addi4spn a2,sp,16','c.addi16sp sp,16','c.mul a2,a3','c.zext.b a2','c.sext.b a2',
            'c.zext.h a2','c.sext.h a2','c.zext.w a2','c.not a2','c.nop']
for instruction in compressed:
    operations+=['add a2,a0,zero','add a3,a1,zero','.option push','.option arch,+zca,+zcb',instruction,'.option pop','add s0,s0,a2']
source=folder/'test.S'
source.write_text('''#ifndef OPERAND_A
#define OPERAND_A 0
#define OPERAND_B 0
#endif
.section .text.init,"ax"
.option norvc
.globl _start,timing_start,timing_end
_start:
  lui t0,0x02000
  sw zero,0(t0)
  la t0,fail
  csrw mtvec,t0
  la t0,fixture
  ld a0,0(t0)
  ld a1,8(t0)
  add sp,a0,zero
  li s0,0
  li s1,0
timing_start:
'''+ '\n'.join(operations)+'''
timing_end:
  lui t0,0x10000
  li t1,0x5a4b5431
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:j 1b
fail:
  lui t0,0x10000
  li t1,1
  sw t1,0x14(t0)
  j 1b
.section .data,"aw"
.balign 8
fixture:
  .quad OPERAND_A
  .quad OPERAND_B
''',encoding='utf-8')
rng=random.Random(0x230d1e1);mask=(1<<64)-1
fixtures=[(0,0),(mask,mask),(0,mask),(mask,0),(1,63),(1<<63,1),
          (0x0123456789abcdef,0xfedcba9876543210),(0x8000000080000000,0xffffffff)]
fixtures += [(rng.getrandbits(64),rng.getrandbits(64)) for _ in range(8)]
baseline=None;text_sha=None;runs=[];observed_results={}
with Simulator() as sim:
  for index,(a,b) in enumerate(fixtures):
    elf=folder/f'{index}.elf';trace=folder/f'{index}.csv';text_file=folder/f'{index}.text.bin'
    compile_record,_=sim.run([GCC/'riscv-none-elf-gcc.exe',
      '-march=rv64gcb_zicond_zcb','-mabi=lp64d','-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
      f'-DOPERAND_A=0x{a:016x}',f'-DOPERAND_B=0x{b:016x}',
      '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/f'{index}.compile.log',60)
    sim.run([GCC/'riscv-none-elf-objcopy.exe','-O','binary','-j','.text',elf,text_file],folder/f'{index}.objcopy.log',60)
    if text_sha is None:text_sha=sha(text_file)
    assert sha(text_file)==text_sha,('instruction bytes differ',index)
    _,symbols=sim.run([GCC/'riscv-none-elf-nm.exe','-n',elf],folder/f'{index}.symbols.log',30)
    labels={line.split()[-1]:int(line.split()[0],16) for line in symbols.splitlines() if len(line.split())==3}
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
      f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit','+timeout_cycles=1000000','+expected_exit_code=0'],folder/f'{index}.simulation.log',120)
    assert 'PASS rv32_program_tb' in text and 'data=0x5a4b5431' in text
    with trace.open(newline='') as stream:
      rows=[r for r in csv.DictReader(stream) if labels['timing_start']<=int(r['pc'],16)<labels['timing_end']]
    assert rows and all(r['trap']=='0' for r in rows),index
    first=int(rows[0]['cycle'])
    profile=[(r['pc'],r['instruction'],int(r['cycle'])-first) for r in rows]
    if baseline is None:baseline=profile
    assert profile==baseline,('data-dependent measured retirement profile',index)
    for row in rows:observed_results.setdefault(row['pc'],set()).add(row['wdata'])
    runs.append({'a':a,'b':b,'compile':compile_record,'run':run,'elf':elf.relative_to(ROOT).as_posix(),
      'elf_sha256':sha(elf),'trace':trace.relative_to(ROOT).as_posix(),'trace_sha256':sha(trace)})
for p,h in {**model['inputs'],**runtime_inputs}.items():assert sha(ROOT/p)==h,p
varied=sum(len(v)>1 for v in observed_results.values());assert varied>100,varied
dump(folder/'report.json',{'passed':True,'scope':'Finite full-core Zkt-directed timing evidence with identical text/control and varied memory data fixtures. Includes additional B/Zicond/Zcb forms. No formal/system-wide security sign-off.',
    'fixtures':len(fixtures),'measured_instructions':len(baseline),'cycles':baseline[-1][2]+1,
    'instructions_with_varied_results':varied,'text_sha256':text_sha,'source_sha256':sha(source),
    'generator_sha256':sha(__file__),'model':model,'runtime_inputs':runtime_inputs,'runs':runs,
    'reference':'https://github.com/riscv/riscv-crypto/blob/main/doc/scalar/riscv-crypto-scalar-zkt.adoc'})
print('PASS native scalar data-independent timing:',len(fixtures),'identical-text fixtures,',len(baseline),'instructions per trace',flush=True)

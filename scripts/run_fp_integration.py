"""Execute independently computed F/D/Zfhmin/Zfa vectors through the whole SoC."""
import csv,json,random,struct
from collections import defaultdict
from sim_runner import ROOT,Simulator,GCC,sha,dump

folder=ROOT/'out/rva23/fp_integration';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/scalar/model.json').read_text())
assert all(f'-G{x}=1' in model['params'] for x in ['HAS_D','HAS_ZFHMIN','HAS_ZFA'])
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
vector_file=ROOT/'out/rva23/fpu/vectors.hex'
groups=defaultdict(list);mask=(1<<64)-1
for line in vector_file.read_text().splitlines():
    p=int(line,16)
    if (p>>86)&1:continue # Reserved encodings have a dedicated trap payload.
    insn=p>>352;frm=(p>>88)&7;flags=(p>>91)&31
    groups[(insn,frm,flags)].append(p)
rng=random.Random(230064);selected=[]
for group in groups.values():
    selected += group[:2]
    if len(group)>2:selected+=rng.sample(group[2:],min(2,len(group)-2))
selected=list(dict.fromkeys(selected))

startup='''.section .text.init,"ax"
.option norvc
.globl _start
_start:
  lui t0,0x02000
  sw zero,0(t0)
  la t0,fail
  csrw mtvec,t0
  li t0,0x6000
  csrs mstatus,t0
  csrr t0,misa
  andi t0,t0,8
  beqz t0,fail
  la s0,records
'''
finish='''
  lui t0,0x10000
  li t1,0x46503634
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
records:
'''
report={'passed':False,'scope':'Full OoO core, 64-bit FP PRF/writeback/LSU and scalar FP execution',
    'model_inputs':model['inputs'],'binary_sha256':model['binary_sha256'],
    'generator_sha256':sha(__file__),'vectors_sha256':sha(vector_file),'cases':len(selected),'runs':[]}
with Simulator() as sim:
    for batch,start in enumerate(range(0,len(selected),600)):
        vectors=selected[start:start+600];code=[startup];data=[];expected={}
        for i,p in enumerate(vectors):
            insn=p>>352;integer=(p>>87)&1;frm=(p>>88)&7;flags=(p>>91)&31
            a=(p>>288)&mask;b=(p>>224)&mask;c=(p>>160)&mask;value=(p>>96)&mask
            family=insn>>27;op=insn&127;rs2=(insn>>20)&31
            # Rename only true operands. Selector/immediate fields stay intact.
            insn=(insn&~(31<<7))|((28 if integer else 3)<<7)
            if op in [0x43,0x47,0x4b,0x4f]:
                insn=(insn&~((31<<15)|(31<<20)|(31<<27)))|(1<<20)|(2<<27)
            elif family==30 and rs2==1:pass # FLI immediate in rs1
            else:
                insn&=~(31<<15)
                if family in [26,30]:insn|=5<<15
                if family in [0,1,2,3,4,5,20]:insn=(insn&~(31<<20))|(1<<20)
            expected[f'test_op_{i}']=(insn,value,integer)
            code += [f'  li s2,{start+i}',
                '  fld ft0,0(s0)','  fld ft1,8(s0)','  fld ft2,16(s0)','  ld t0,0(s0)',
                '  csrw fcsr,zero',f'  li t1,{frm}','  csrw frm,t1',
                f'.globl test_op_{i}',f'test_op_{i}:',f'  .word 0x{insn:08x}']
            if not integer:code+=['  fmv.x.d t3,ft3']
            code+=['  ld t1,24(s0)','  bne t3,t1,fail','  csrr t3,fflags',
                   '  ld t1,32(s0)','  bne t3,t1,fail','  addi s0,s0,48']
            data += [f'  .quad 0x{x:016x}' for x in [a,b,c,value,flags,frm]]
        source=folder/f'batch_{batch}.S';elf=source.with_suffix('.elf');trace=source.with_suffix('.csv')
        source.write_text('\n'.join(code)+finish+'\n'.join(data)+'\n')
        sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imafdc_zfhmin_zfa_zicsr_zifencei','-mabi=lp64d',
            '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
            '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/f'compile_{batch}.log',60)
        _,symbols=sim.run([GCC/'riscv-none-elf-nm.exe','-n',elf],folder/f'symbols_{batch}.log',60)
        addresses={int(parts[0],16):expected[parts[2]] for line in symbols.splitlines()
                   if len(parts:=line.split())==3 and parts[2] in expected}
        assert len(addresses)==len(vectors)
        run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
            '+timeout_cycles=3000000','+expected_exit_code=0'],folder/f'simulation_{batch}.log',180)
        assert 'data=0x46503634' in text and 'PASS rv32_program_tb' in text
        with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
        assert not any(r['trap']=='1' and int(r['pc'],16)>=0x80000000 for r in rows)
        retired=[r for r in rows if int(r['pc'],16) in addresses]
        assert len(retired)==len(vectors),(len(retired),len(vectors))
        for r in retired:
            insn,value,integer=addresses[int(r['pc'],16)]
            assert int(r['instruction'],16)==insn,r
            assert int(r['wdata'],16)==value,(r,hex(value))
        fresh()
        report['runs'].append({'batch':batch,'cases':len(vectors),'elf_sha256':sha(elf),
            'source_sha256':sha(source),'run':run,'trace_sha256':sha(trace)})
        dump(folder/'report.json',report)
        print('PASS full-core scalar FP batch',batch,'cases',len(vectors),flush=True)
report['passed']=True;dump(folder/'report.json',report)
print('PASS integrated FP exact cases',len(selected),flush=True)

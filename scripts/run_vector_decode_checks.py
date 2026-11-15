"""GNU opcode oracle for every RVV/Zvbb form and scalar operand namespace."""
import json,struct
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/vector_decode';folder.mkdir(parents=True,exist_ok=True)
table=json.loads((ROOT/'config/vector_opcode_tables/encodings.json').read_text())
assert sha(ROOT/'rtl/backend/rv_vector_decode_pkg.sv')==table['rtl_sha256']
instructions=table['instructions'];assembly=[];expect=[]
for index,e in enumerate(instructions,1):
    name=e['name'];args=e['arguments'];op=e['match']&127;f3=(e['match']>>12)&7
    fp=op==0x57 and f3 in [1,5]
    if name.startswith('vset'):
        operands={'vsetvl':'a2,a0,a1','vsetvli':'a2,a0,e32,m1,tu,mu','vsetivli':'a2,3,e32,m1,tu,mu'}[name]
    elif op in [7,0x27]:
        operands='v8,(a0)'
        if 'rs2' in args:operands+=',a1'
        if 'vs2' in args:operands+=',v16'
    else:
        result='fa2' if name=='vfmv.f.s' else ('a2' if 'rd' in args else 'v8')
        sources=[]
        if 'vs2' in args:sources.append('v16')
        if 'vs1' in args:sources.append('v24')
        if 'rs1' in args:sources.append('fa0' if fp else 'a0')
        if 'simm5' in args:sources.append('-3')
        if 'zimm5' in args:sources.append('3')
        if 'zimm6lo' in args:sources.append('63')
        # Accumulating forms name the multiplicand before vs2 in assembly.
        stem=name.split('.')[0]
        if stem in ['vmadd','vnmsub','vmacc','vnmsac','vwmaccu','vwmacc','vwmaccsu','vwmaccus',
                    'vfmadd','vfnmadd','vfmsub','vfnmsub','vfmacc','vfnmacc','vfmsac','vfnmsac',
                    'vfwmacc','vfwnmacc','vfwmsac','vfwnmsac']:sources.reverse()
        operands=','.join([result,*sources])
        if name.endswith(('vvm','vxm','vim')) or name=='vfmerge.vfm':operands+=',v0'
    meta=(int(name.startswith('vset'))<<0)|(int(op in [7,0x27])<<1)|(int(op==0x27)<<2)|(int(fp)<<3)
    meta|=(int('rs1' in args)<<4)|(int('rs2' in args)<<5)|(int(fp and 'rs1' in args)<<6)
    meta|=(int('rd' in args)<<7)|(int(name=='vfmv.f.s')<<8)
    assembly.append(name+' '+operands);expect.append((index,meta,e['extension']=='ZVBB'))
    if 'vm' in args:
        assembly.append(name+' '+operands+',v0.t');expect.append((index,meta,e['extension']=='ZVBB'))
source=folder/'test.S';source.write_text('.text\n.option norvc\n'+'\n'.join(assembly)+'\n')
with Simulator() as sim:
    obj=folder/'test.o';binary=folder/'test.bin'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcv_zvbb','-mabi=lp64d','-c',source,'-o',obj],folder/'assemble.log',60)
    sim.run([GCC/'riscv-none-elf-objcopy.exe','-O','binary','-j','.text',obj,binary],folder/'objcopy.log',60)
    code=binary.read_bytes();assert len(code)==4*len(expect)
    lines=[]
    for i,(op,meta,zvbb) in enumerate(expect):
        insn=struct.unpack_from('<I',code,4*i)[0]
        lines.append(f'{insn:08x}{op:04x}{meta:04x}{int(zvbb):08x}')
    vectors=folder/'vectors.hex';vectors.write_text('\n'.join(lines)+'\n')
    model=sim.build('rva23_vector_decode','rv_vector_decode_tb',[
        'rtl/backend/rv_vector_decode_pkg.sv','tb/unit/backend/rv_vector_decode_tb.sv'],[
        f'-GCOUNT={len(lines)}',f'-GFILE="{vectors.relative_to(ROOT).as_posix()}"'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'391 encoding forms and scalar namespaces; vector execution not implied',
        'forms':len(instructions),'gnu_vectors':len(lines),'source_sha256':sha(source),'vectors_sha256':sha(vectors),
        'generator_sha256':sha(__file__),'opcode_table_sha256':sha(ROOT/'config/vector_opcode_tables/encodings.json'),'model':model})
    print('PASS GNU vector encoding/namespace oracle',len(instructions),'forms',len(lines),'vectors',flush=True)

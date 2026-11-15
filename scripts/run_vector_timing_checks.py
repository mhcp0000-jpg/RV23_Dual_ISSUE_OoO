"""Paired vector latency checks with identical control and different data.

Finite evidence for the Zvkt implementation audit, not a formal proof or a
whole-core timing/security sign-off. Checks a stronger integer subset too.
"""
import csv,json,random,struct
from sim_runner import ROOT,Simulator,GCC,sha,dump,source_inputs

folder=ROOT/'out/rva23/vector_timing';folder.mkdir(parents=True,exist_ok=True)
table=json.loads((ROOT/'config/vector_opcode_tables/encodings.json').read_text())
forms=[]
for index,e in enumerate(table['instructions'],1):
    name=e['name'];args=e['arguments'];op=e['match']&127;f3=(e['match']>>12)&7
    fp=op==0x57 and f3 in [1,5]
    if name.startswith('vset') or op in [7,0x27] or (fp and not name.startswith('vfslide1')):continue
    dest='a2' if 'rd' in args else 'v8';sources=[]
    if 'vs2' in args:sources.append('v16')
    if 'vs1' in args:sources.append('v24')
    if 'rs1' in args:sources.append('fa0' if fp else 'a0')
    if 'simm5' in args:sources.append('-3')
    if 'zimm5' in args:sources.append('3')
    if 'zimm6lo' in args:sources.append('63')
    stem=name.split('.')[0]
    if stem in ['vmadd','vnmsub','vmacc','vnmsac','vwmaccu','vwmacc','vwmaccsu','vwmaccus']:sources.reverse()
    asm=name+' '+','.join([dest,*sources])
    if name.endswith(('vvm','vxm','vim')):asm+=',v0'
    forms.append({'id':index,'name':name,'assembly':asm,'mask_data':stem in ['vadc','vmadc','vsbc','vmsbc','vmerge']})
    if 'vm' in args:forms.append({'id':index,'name':name,'assembly':asm+',v0.t','mask_data':False})

assembly=['vsetvl a2,a0,a1']+[f'vmv.v.x v{i},a0' for i in range(32)]+[e['assembly'] for e in forms]
source=folder/'instructions.S';source.write_text('.text\n.option norvc\n'+'\n'.join(assembly)+'\n')
rng=random.Random(0x2300d1e1);allones=(1<<64)-1;packets=[]
with Simulator() as sim:
    obj=folder/'instructions.o';code=folder/'instructions.bin'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcv_zvbb','-mabi=lp64d','-c',source,'-o',obj],folder/'assemble.log',60)
    sim.run([GCC/'riscv-none-elf-objcopy.exe','-O','binary','-j','.text',obj,code],folder/'objcopy.log',60)
    binary=code.read_bytes();assert len(binary)==4*len(assembly)
    instructions=list(struct.unpack('<'+'I'*len(assembly),binary))
    def emit(insn,a0=0,b0=0,a1=None,b1=None,group=0):
        packets.append([group,insn,a0&allones,b0&allones,(a0 if a1 is None else a1)&allones,(b0 if b1 is None else b1)&allones])
    configurations=[]
    for sew in range(4):
      for exponent in range(-3,4):
        if (8<<sew)>64*(2**exponent):continue
        maximum=int(128*(2**exponent)/(8<<sew))
        for length in sorted({0,1,maximum}):
          for pattern in range(3):
            emit(instructions[0],2,24) # fill all 128 bits of each register as e64,m1
            for reg in range(32):
                if reg==0:x=y=0xaaaaaaaaaaaaaaaa # same execution mask
                elif pattern==0:x=0;y=allones
                elif pattern==1:x=1<<(reg%64);y=allones^x
                else:x=rng.getrandbits(64);y=rng.getrandbits(64)
                emit(instructions[1+reg],x,a1=y)
            emit(instructions[0],length,(sew<<3)|(exponent&7))
            for i,e in enumerate(forms):
                if e['mask_data']:emit(instructions[1],0,a1=allones)
                emit(instructions[33+i],rng.getrandbits(64),0,a1=rng.getrandbits(64),group=e['id'])
                if e['mask_data']:emit(instructions[1],0xaaaaaaaaaaaaaaaa)
            configurations.append({'sew':8<<sew,'lmul_exponent':exponent,'vl':length,'pattern':pattern})
    vectors=folder/'vectors.hex'
    vectors.write_text('\n'.join(' '.join(f'{v:x}' for v in row) for row in packets)+'\n')
    files=(ROOT/'rtl/filelist.f').read_text().splitlines()+['tb/unit/backend/rv_vector_timing_tb.sv']
    model_path=folder/'model.json'
    old=json.loads(model_path.read_text()) if model_path.exists() else None
    if old and old['inputs']==source_inputs(files) and sha(ROOT/old['binary'])==old['binary_sha256']:model=old
    else:
        model=sim.build('rva23_vector_timing','rv_vector_timing_tb',files)
        dump(model_path,model)
    latencies=folder/'latencies.csv'
    model['run']=sim.simulate(model,[f'+vectors={vectors.relative_to(ROOT).as_posix()}',f'+latencies={latencies.relative_to(ROOT).as_posix()}'],timeout=240)
    with latencies.open(newline='') as stream:rows=list(csv.DictReader(stream))
    covered={int(r['group']) for r in rows if r['illegal']=='0'}
    required={e['id'] for e in forms};assert covered==required,{'missing_legal_forms':sorted(required-covered)}
    model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'Finite paired vector-owner latency evidence; common configuration/masks and varied scalar/vector data. Includes integer operations beyond Zvkt and VF slides. No whole-core/formal security sign-off.',
        'forms':len(required),'encoding_variants':len(forms),'configurations':configurations,'paired_probes':len(rows),
        'packets':len(packets),'model':model,'source_sha256':sha(source),'vector_sha256':sha(vectors),
        'latencies_sha256':sha(latencies),'generator_sha256':sha(__file__),
        'reference':'https://github.com/riscv/riscv-crypto/blob/main/doc/vector/riscv-crypto-vector-zvkt.adoc'})
print('PASS paired vector latency:',len(rows),'probes,',len(required),'forms',flush=True)

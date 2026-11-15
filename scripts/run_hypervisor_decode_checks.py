"""Exact GNU H/HINVAL encodings and M/HS/U/VS/VU permission matrix."""
import json,random,struct
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/hypervisor_decode';folder.mkdir(parents=True,exist_ok=True)
sources=json.loads((ROOT/'config/hypervisor_opcode_tables/sources.json').read_text())
for record in sources:assert sha(ROOT/record['file'])==record['sha256']
forms=[]
for file in ['rv_h','rv64_h','rv_svinval_h']:
    for line in (ROOT/'config/hypervisor_opcode_tables'/file).read_text().splitlines():
        line=line.partition('#')[0].strip()
        if not line:continue
        name,*tokens=line.split();mask=match=0;arguments=[]
        for token in tokens:
            if '=' not in token:arguments.append(token);continue
            key,value=token.split('=');parts=key.split('..');high=int(parts[0]);low=int(parts[-1]);value=int(value,0)
            mask|=((1<<(high-low+1))-1)<<low;match|=value<<low
        forms.append({'name':name,'mask':mask,'match':match,'arguments':arguments,'rv64':file=='rv64_h'})
rng=random.Random(0x4859504552);program=[]
for form in forms:
    name=form['name']
    for i in range(36):
        rd=i%32;rs1=(i*7)%32;rs2=rng.randrange(32)
        if name.startswith(('hfence','hinval')):asm=f'{name} x{rs1},x{rs2}'
        elif name.startswith('hsv'):asm=f'{name} x{rs2},(x{rs1})'
        else:asm=f'{name} x{rd},(x{rs1})'
        program.append((form,asm))
source=folder/'program.S';source.write_text('.text\n.option norvc\n'+'\n'.join(asm for _,asm in program)+'\n')
def expected(form,insn):
    name=form['name'];fence=name.startswith(('hfence','hinval'));store=name.startswith('hsv')
    size={'b':0,'bu':0,'h':1,'hu':1,'w':2,'wu':2,'d':3}.get(name.partition('.')[2],0)
    values=[1,int(not fence),int(store),int(name.startswith('hlvx')),int(fence),int(name.endswith('gvma')),
            int(name.startswith('hinval')),size,int(name.endswith(('bu','hu','wu'))),3 if fence or store else 1,
            int(not fence and not store and (insn>>7)&31!=0)]
    # Packed SV struct order, leftmost member is the most significant bit.
    result=0
    for value,width in zip(values,[1]*7+[2,1,2,1]):result=(result<<width)|value
    return result
vectors=[]
with Simulator() as sim:
    obj=folder/'program.o';binary=folder/'program.bin'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gch_svinval','-mabi=lp64d','-c',source,'-o',obj],folder/'assemble.log',60)
    sim.run([GCC/'riscv-none-elf-objcopy.exe','-O','binary','-j','.text',obj,binary],folder/'objcopy.log',60)
    data=binary.read_bytes();assert len(data)==4*len(program)
    samples=[]
    for i,(form,asm) in enumerate(program):
        insn=struct.unpack_from('<I',data,i*4)[0];assert insn&form['mask']==form['match'],asm
        samples.append(insn)
        # Every fixed-bit mutation is checked against the complete encoding
        # table, since some mutations legitimately select another H operation.
        samples.extend(insn^(1<<bit) for bit in range(32) if form['mask']>>bit&1)
    samples=sorted(set(samples))
    for insn in samples:
        matches=[f for f in forms if insn&f['mask']==f['match']];assert len(matches)<=1
        form=matches[0] if matches else None
        for xlen in [32,64]:
            for inval in [0,1]:
                valid=bool(form and not(form['rv64'] and xlen==32) and not(form['name'].startswith('hinval') and not inval))
                value=expected(form,insn) if valid else 0
                for priv,virt in [(3,0),(1,0),(0,0),(1,1),(0,1)]:
                    for hu,tvm in [(0,0),(1,0),(0,1),(1,1)]:
                        exc=valid and (virt or (priv==0 and (form['name'].startswith(('hfence','hinval')) or not hu)) or
                            (priv==1 and not virt and form['name'].endswith('gvma') and tvm))
                        cause=22 if valid and virt else 2
                        vectors.append(f'{insn:08x} {xlen} {inval} {priv} {virt} {hu} {tvm} {value:04x} {int(exc):x} {cause:02x}')
    vector=folder/'vectors.hex';vector.write_text('\n'.join(vectors)+'\n')
    model=sim.build('rva23_hypervisor_decode','rv_hypervisor_decode_tb',[
        'rtl/backend/rv_hypervisor_decode_pkg.sv','tb/unit/backend/rv_hypervisor_decode_tb.sv'])
    model['run']=sim.simulate(model,[f'+vectors={vector.relative_to(ROOT).as_posix()}']);model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'H/HINVAL encoding and privilege component only; architectural H integration pending',
        'forms':len(forms),'gnu_vectors':len(program),'encoding_permission_cases':len(vectors),'model':model,
        'opcode_sources':sources,'source_sha256':sha(source),'vectors_sha256':sha(vector),'generator_sha256':sha(__file__)})
    print('PASS H decoder forms',len(forms),'GNU instructions',len(program),'encoding/permission cases',len(vectors),flush=True)

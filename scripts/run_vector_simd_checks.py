"""Independent packed element arithmetic for two subdivided 64-bit lanes."""
import json
import random
from vector_integer_reference import calculate
from sim_runner import ROOT, Simulator, dump, sha

folder=ROOT/'out/rva23/vector_simd';folder.mkdir(parents=True,exist_ok=True)
table=json.loads((ROOT/'config/vector_opcode_tables/encodings.json').read_bytes())
assert table['rtl_sha256']==sha(ROOT/'rtl/backend/rv_vector_decode_pkg.sv')
excluded={'vdiv','vdivu','vrem','vremu','vnsrl','vnsra','vnclip','vnclipu','vzext','vsext',
    'vmand','vmandn','vmor','vmorn','vmnand','vmnor','vmxor','vmxnor'}
rng=random.Random(0x1282064);lines=[];forms=set();width_counts={}
for size in range(4):
    width=8<<size;mask=(1<<width)-1;elements=128//width;count=0
    special=[0,1,mask,1<<(width-1),(1<<(width-1))-1,mask-1,3,7]
    for op_id,op in enumerate(table['integer_operations'],1):
        if op in excluded or op.startswith(('vw','vred')):continue
        if not calculate(op,width,0,0,0,0,False,0,0)[2]:continue
        forms.add(op)
        for rm in range(4):
            for pattern in range(8):
                a=b=c=result=sat=carry=0
                for element in range(elements):
                    av=special[(pattern+element)%8] if pattern<6 else rng.getrandbits(width)
                    bv=special[(pattern+3*element+op_id)%8] if pattern<6 else rng.getrandbits(width)
                    cv=rng.getrandbits(width);bit=rng.randrange(2)
                    value,clipped,supported=calculate(op,width,av,bv,cv,bit,False,rm,0)
                    assert supported and value<=mask
                    a|=av<<(element*width);b|=bv<<(element*width);c|=cv<<(element*width)
                    result|=value<<(element*width);sat|=int(clipped)<<element;carry|=bit<<element
                lines.append(f'{op_id:x} {size:x} {rm:x} 0 {a:032x} {b:032x} {c:032x} {carry:04x} {result:032x} {sat:04x}')
                count+=1
    width_counts[width]=count
# Extension operands occupy destination-width slots; upper source bits are
# intentionally random so sign/zero extension must use the declared EEW.
for size in range(1,4):
    width=8<<size;elements=128//width
    for factor in range(1,size+1):
        source_width=width>>factor
        for op in ['vzext','vsext']:
            forms.add(op);op_id=table['integer_operations'].index(op)+1
            for pattern in range(64):
                a=result=0
                for e in range(elements):
                    value=rng.getrandbits(width)
                    value=(value&~((1<<source_width)-1)) | ([0,1,(1<<source_width)-1,1<<(source_width-1)][(pattern+e)%4] if pattern<16 else rng.getrandbits(source_width))
                    expected,clipped,supported=calculate(op,width,value,0,0,0,False,0,factor)
                    assert supported and not clipped
                    a|=value<<(e*width);result|=expected<<(e*width)
                lines.append(f'{op_id:x} {size:x} 0 {factor:x} {a:032x} 0 0 0 {result:032x} 0')
                width_counts[width]+=1

vectors=folder/'vectors.hex';vectors.write_text('\n'.join(lines)+'\n')
with Simulator() as sim:
    model=sim.build('vector_simd','rv_vector_simd_alu_tb',[
        'rtl/backend/rv_vector_decode_pkg.sv','rtl/backend/rv_vector_integer_alu.sv',
        'rtl/backend/rv_vector_simd_alu.sv','tb/rv_vector_simd_alu_tb.sv'])
    run=sim.simulate(model,[f'+vectors={vectors.relative_to(ROOT).as_posix()}'])
assert f'cases={len(lines)}' in (ROOT/run['log']).read_text()
dump(folder/'report.json',dict(passed=True,scope='Packed ordinary integer ALU arithmetic; full owner/memory/physical timing have separate evidence',
    model=model,run=run,driver_sha256=sha(__file__),oracle_sha256=sha(ROOT/'scripts/vector_integer_reference.py'),
    vectors_sha256=sha(vectors),cases=len(lines),forms=sorted(forms),width_counts=width_counts))
print('PASS two-lane SIMD arithmetic',len(lines),'vectors;',len(forms),'forms;',width_counts)

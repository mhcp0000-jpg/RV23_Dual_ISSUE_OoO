"""Exact element math for every integer operation class and each legal SEW."""
import json,random
from sim_runner import ROOT,Simulator,sha,dump
from vector_integer_reference import calculate
folder=ROOT/'out/rva23/vector_integer';folder.mkdir(parents=True,exist_ok=True)
table=json.loads((ROOT/'config/vector_opcode_tables/encodings.json').read_text())
assert table['rtl_sha256']==sha(ROOT/'rtl/backend/rv_vector_decode_pkg.sv')
report={'passed':False,'scope':'Integer vector element ALU only; vector execution/native core integration has separate evidence',
    'oracle_sha256':sha(ROOT/'scripts/vector_integer_reference.py'),'generator_sha256':sha(__file__),'cases':[]}
rng=random.Random(230128)
with Simulator() as sim:
    for width in [8,16,32,64]:
        special=[0,1,2,3,(1<<(width-1))-1,1<<(width-1),(1<<(width-1))+1,
            (1<<width)-2,(1<<width)-1,(1<<64)-1,0x0123456789abcdef]
        lines=[];math_cases=0;unsupported_cases=0
        for op_id,op in enumerate(table['integer_operations'],1):
            pairs=[(a,b,rng.getrandbits(64)) for a in special for b in special]
            pairs += [(rng.getrandbits(64),rng.getrandbits(64),rng.getrandbits(64)) for _ in range(60)]
            for rm in range(4):
                for i,(a,b,c) in enumerate(pairs):
                    carry=i%2;wide=(i//2)%2;ext=(i//4)%4
                    result,sat,supported=calculate(op,width,a,b,c,carry,wide,rm,ext)
                    math_cases+=supported;unsupported_cases+=not supported
                    lines.append(f'{op_id:x} {a:016x} {b:016x} {c:016x} {carry:x} {wide:x} {rm:x} {ext:x} {result:016x} {int(sat):x} {int(supported):x}')
        path=folder/f'w{width}.hex';path.write_text('\n'.join(lines)+'\n')
        model=sim.build(f'rva23_vector_integer_{width}','rv_vector_integer_alu_tb',[
            'rtl/backend/rv_vector_decode_pkg.sv','rtl/backend/rv_vector_integer_alu.sv',
            'tb/unit/backend/rv_vector_integer_alu_tb.sv'],[f'-GWIDTH={width}'])
        model['run']=sim.simulate(model,[f'+vectors={path.relative_to(ROOT).as_posix()}']);model['passed']=True
        report['cases'].append({'width':width,'math_cases':math_cases,'unsupported_classes':unsupported_cases,
            'vectors':len(lines),'vector_sha256':sha(path),'model':model})
        dump(folder/'report.json',report);print('PASS vector integer element width',width,'exact math',math_cases,'unsupported checks',unsupported_cases,flush=True)
    report['passed']=True;dump(folder/'report.json',report)

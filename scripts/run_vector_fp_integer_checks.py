"""Exact conversion flags/data for all vector integer widths and FP32/64."""
import json,random
from fractions import Fraction
from sim_runner import ROOT,Simulator,sha,dump
from fp_reference import BinaryFP
folder=ROOT/'out/rva23/vector_fp_integer';folder.mkdir(parents=True,exist_ok=True)
rng=random.Random(230016);lines=[]
for fp_double in [0,1]:
    fp=BinaryFP(11,52) if fp_double else BinaryFP(8,23)
    for int_size in range(4):
        bits=8<<int_size
        for unsigned in [False,True]:
            for to_float in [False,True]:
                inputs=[0,1,2,(1<<(bits-1))-1,1<<(bits-1),(1<<(bits-1))+1,(1<<bits)-1,(1<<64)-1]
                if not to_float:
                    inputs=[0,fp.signbit,1,fp.fracmask,fp.inf,fp.inf|fp.signbit,fp.nan,fp.inf|1,fp.mask]
                    for value in [0,1,-1,(1<<bits)-1,1<<bits,-(1<<(bits-1)),(1<<(bits-1))-1]:
                        for offset in [Fraction(-3,4),Fraction(-1,2),Fraction(-1,4),Fraction(0),Fraction(1,4),Fraction(1,2),Fraction(3,4)]:
                            inputs.append(fp.pack(Fraction(value)+offset,0)[0])
                inputs += [rng.getrandbits(64 if to_float else fp.width) for _ in range(180)]
                for rm in range(5):
                    for operand in inputs:
                        result,flags=fp.from_int(operand,bits,unsigned,rm) if to_float else fp.to_int(operand,bits,unsigned,rm)
                        if not to_float:result&=(1<<bits)-1
                        lines.append(f'{fp_double:x} {int_size:x} {int(unsigned):x} {int(to_float):x} {rm:x} {operand:016x} {result:016x} {flags:02x}')
vector=folder/'vectors.hex';vector.write_text('\n'.join(lines)+'\n')
provenance=json.loads((ROOT/'rtl/vendor/hardfloat/PROVENANCE.json').read_text())
files=[x['path'] for x in provenance['files'] if x['path'].endswith('.v')]+[
    'rtl/backend/rv_vector_fp_integer.sv','tb/unit/backend/rv_vector_fp_integer_tb.sv']
with Simulator() as sim:
    model=sim.build('rva23_vector_fp_integer','rv_vector_fp_integer_tb',files)
    model['run']=sim.simulate(model,[f'+vectors={vector.relative_to(ROOT).as_posix()}']);model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'Vector integer/FP element conversion only; vector FP/native core integration has separate evidence',
        'vectors':len(lines),'vector_sha256':sha(vector),'generator_sha256':sha(__file__),
        'oracle_sha256':sha(ROOT/'scripts/fp_reference.py'),'model':model})
    print('PASS vector FP/int exact conversions',len(lines),flush=True)

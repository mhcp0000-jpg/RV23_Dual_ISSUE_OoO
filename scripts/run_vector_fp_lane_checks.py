"""Every GNU vector-FP form through the lane, with exact IEEE/Spike oracles."""
import json,random
from fractions import Fraction
from sim_runner import ROOT,Simulator,sha,dump
from vector_fp_reference import interpret,formats,boxed,MASK
folder=ROOT/'out/rva23/vector_fp_lane';folder.mkdir(parents=True,exist_ok=True)
encodings=json.loads((ROOT/'config/vector_opcode_tables/encodings.json').read_text())['instructions']
decode_report=json.loads((ROOT/'out/rva23/vector_decode/report.json').read_text());assert decode_report['passed']
decode_vectors=ROOT/'out/rva23/vector_decode/vectors.hex';assert sha(decode_vectors)==decode_report['vectors_sha256']
codes={}
for line in decode_vectors.read_text().splitlines():codes.setdefault(int(line[8:12],16),int(line[:8],16))
forms=[(e['name'],codes[i]) for i,e in enumerate(encodings,1) if e['match']&127==0x57 and (e['match']>>12)&7 in [1,5]]

def special(size,estimate=False):
    f=formats[size];one=f.bias<<f.fb
    if estimate:return [0,f.signbit,1,f.fracmask,1<<f.fb,one,one|f.signbit,
        f.inf-(1<<f.fb),f.inf-1,f.inf,f.inf|f.signbit,f.nan,f.inf|(1<<(f.fb-7))]
    return [0,f.signbit,1,f.signbit|1,f.fracmask,1<<f.fb,(1<<f.fb)|1,
        one,one|f.signbit,one-1,one+1,f.inf-1,f.inf,f.inf|f.signbit,f.nan,f.inf|1,f.mask]

wanted_estimates=set()
for size in [2,3]:
    for a in special(size,True):
        for sqrt in [0,1]:
            for rm in range(5):wanted_estimates.add((8<<size,sqrt,rm,a))
estimates={};estimate_path=ROOT/'out/rva23/vector_estimates/vectors.txt'
estimate_report=json.loads((ROOT/'out/rva23/vector_estimates/report.json').read_text());assert estimate_report['passed']
assert sha(estimate_path)==estimate_report['vectors_sha256']
with estimate_path.open() as stream:
    for line in stream:
        width,sqrt,rm,a,result,flags=line.split();key=(int(width),int(sqrt),int(rm),int(a,16))
        if key in wanted_estimates:estimates[key]=(int(result,16),int(flags,16))
assert estimates.keys()==wanted_estimates,(wanted_estimates-estimates.keys())

lines=[];rng=random.Random(230064);valid_cases=illegal_cases=0
def append(name,insn,sew,rm,a,b,c,mask):
    global valid_cases,illegal_cases
    result,flags,illegal=interpret(name,insn,sew,rm,a,b,c,mask,estimates)
    illegal_cases+=illegal;valid_cases+=not illegal
    lines.append(f'{insn:08x} {sew:x} {rm:x} {mask:x} {a:016x} {b:016x} {c:016x} {result&MASK:016x} {flags:02x} {int(illegal):x}')
for name,insn in forms:
    family=insn>>26;selector=(insn>>15)&31;scalar=(insn>>12)&7==5
    estimate=family==19 and selector in [4,5]
    for sew in [1,2,3]:
        conversion=family==18;narrow=conversion and bool(selector&16)
        source_size=min(3,sew+int(narrow))
        if family in [0x34,0x36]:source_size=3 # .wf/.wv consume an already-wide vs2
        from_integer=conversion and (selector&7) in [2,3]
        values=special(source_size,estimate and sew>=2)
        if from_integer:values=[0,1,(1<<15)-1,1<<15,(1<<16)-1,(1<<31)-1,1<<31,(1<<32)-1,(1<<63)-1,1<<63,MASK]
        if conversion and (selector&7) in [0,1,6,7]:
            f=formats[source_size]
            for value in [-32769,-32768,32767,32768,65535,65536]:
                for offset in [Fraction(-1,2),Fraction(0),Fraction(1,2)]:values.append(f.pack(Fraction(value)+offset,0)[0])
        if not estimate:values += [rng.getrandbits(64 if from_integer else (8<<source_size)) for _ in range(30)]
        bsize=3 if family in [0x31,0x33] else sew
        csize=3 if family>=0x30 else sew
        for rm in range(5):
            for i,a in enumerate(values):
                b=special(bsize)[(i*7+3)%len(special(bsize))]
                c=special(csize)[(i*11+5)%len(special(csize))]
                if scalar and sew==2:b=boxed(b,sew)
                append(name,insn,sew,rm,a,b,c,i%2)
        for rm in [5,6,7]:append(name,insn,sew,rm,0,0,0,0)
        # A non-boxed VF scalar must become a canonical NaN, while vector
        # source bits never undergo scalar NaN-box validation.
        if scalar and sew==2:
            for value in [1,0x7f800001,0x3f800000,0x12345678deadbeef]:
                append(name,insn,sew,0,0x3f800000,value,0x40000000,1)
vectors=folder/'vectors.hex';vectors.write_text('\n'.join(lines)+'\n')
vendor=json.loads((ROOT/'rtl/vendor/hardfloat/PROVENANCE.json').read_text())
files=['rtl/rv_ooo_pkg.sv','rtl/backend/rv_fp_decode_pkg.sv','rtl/backend/rv_vector_decode_pkg.sv',
    'rtl/backend/rv_vector_estimate_tables_pkg.sv']+[
    x['path'] for x in vendor['files'] if x['path'].endswith('.v')]+[
    'rtl/backend/'+name+'.sv' for name in ['rv_fp_format','rv_fp_convert','rv_fp_round_to_int',
    'rv_fp_immediate','rv_fp_cvtmod','rv_fpu_rva23','rv_vector_fp_integer','rv_vector_fp_estimate','rv_vector_fp_lane']]+[
    'tb/unit/backend/rv_vector_fp_lane_tb.sv']
with Simulator() as sim:
    model=sim.build('rva23_vector_fp_lane','rv_vector_fp_lane_tb',files)
    model['run']=sim.simulate(model,[f'+vectors={vectors.relative_to(ROOT).as_posix()}']);model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'Vector FP lane only; vector controller/core FP integration remains pending',
        'forms':len(forms),'valid_cases':valid_cases,'illegal_cases':illegal_cases,'vectors':len(lines),
        'vector_sha256':sha(vectors),'generator_sha256':sha(__file__),
        'oracle_inputs':{p:sha(ROOT/p) for p in ['scripts/vector_fp_reference.py','scripts/fp_reference.py',
            'out/rva23/vector_estimates/report.json','out/rva23/vector_decode/report.json']},'model':model})
    print('PASS vector FP lane GNU forms',len(forms),'valid exact cases',valid_cases,'illegal contexts',illegal_cases,flush=True)

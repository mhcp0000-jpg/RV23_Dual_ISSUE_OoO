"""Exact oracle for NaN boxing, format conversions and remaining Zfa datapaths."""
import json,random
from fractions import Fraction
from sim_runner import ROOT,Simulator,sha,dump
from fp_reference import BinaryFP,round_int,NX,NV
folder=ROOT/'out/rva23/fp_aux';folder.mkdir(parents=True,exist_ok=True)
formats=[BinaryFP(8,23),BinaryFP(11,52),BinaryFP(5,10)]
mask64=(1<<64)-1;rng=random.Random(0xF2365);vectors=[]
def box(value,f):return value|((~f.mask)&mask64)
def add(kind,source,destination,rm,nx,operand,result,flags):
    value=(kind<<380)|(destination<<378)|(source<<376)|(rm<<373)|(nx<<372)|(operand<<288)|(result<<96)|(flags<<91)
    vectors.append(f'{value:096x}')
def corners(f):
    one=f.bias<<f.fb
    return [0,f.signbit,1,f.signbit|1,f.fracmask,1<<f.fb,one,one|f.signbit,one-1,one+1,
        f.inf-1,f.inf,f.inf|f.signbit,f.nan,f.nan|1,f.inf|1,f.mask,
        ((f.bias-1)<<f.fb),((f.bias-1)<<f.fb)|f.signbit]
for src,sf in enumerate(formats):
    for dst,df in enumerate(formats):
        for rm in range(5):
            values=corners(sf)+[rng.getrandbits(sf.width) for _ in range(64)]
            for value in values:
                result,flags=df.convert(value,sf,rm)
                add(0,src,dst,rm,0,box(value,sf),box(result,df),flags)
            if src!=1:
                # Non-boxed inputs are canonical quiet NaNs, including when
                # their low bits happen to encode a signaling NaN or finite.
                for value in [1,sf.inf|1,sf.nan]:
                    result,flags=df.convert(sf.nan,sf,rm)
                    add(0,src,dst,rm,0,value,box(result,df),flags)
for fmt,f in enumerate(formats[:2]):
    for rm in range(5):
        for nx in [0,1]:
            for value in corners(f)+[rng.getrandbits(f.width) for _ in range(100)]:
                flags=0
                if f.is_nan(value):result=f.nan;flags=NV if f.is_snan(value) else 0
                elif f.is_inf(value) or f.is_zero(value):result=value
                else:
                    v=f.value(value);q,inexact=round_int(abs(v).numerator,abs(v).denominator,v<0,rm)
                    if v<0:q=-q
                    result,_=f.pack(Fraction(q),rm,f.sign(value))
                    flags=NX if nx and inexact else 0
                add(1,0,fmt,rm,nx,value,box(result,f),flags)
    table=[-1,None,Fraction(1,1<<16),Fraction(1,1<<15),Fraction(1,256),Fraction(1,128),
        Fraction(1,16),Fraction(1,8),Fraction(1,4),Fraction(5,16),Fraction(3,8),Fraction(7,16),
        Fraction(1,2),Fraction(5,8),Fraction(3,4),Fraction(7,8),1,Fraction(5,4),Fraction(3,2),
        Fraction(7,4),2,Fraction(5,2),3,4,8,16,128,256,32768,65536,None,None]
    for index,value in enumerate(table):
        if index==1:result=1<<f.fb
        elif index==30:result=f.inf
        elif index==31:result=f.nan
        else:result,_=f.pack(Fraction(value),0)
        add(2,0,fmt,0,0,index,box(result,f),0)
f=formats[1]
for value in corners(f)+[rng.getrandbits(64) for _ in range(1000)]:
    if f.is_nan(value) or f.is_inf(value):result=0
    else:
        v=f.value(value);q=abs(v.numerator)//v.denominator
        if v<0:q=-q
        result=q&0xffffffff
        if result>>31:result|=0xffffffff00000000
    add(3,0,1,0,0,value,result,0)
path=folder/'vectors.hex';path.write_text('\n'.join(vectors)+'\n',encoding='utf-8')
provenance=json.loads((ROOT/'rtl/vendor/hardfloat/PROVENANCE.json').read_text())
for item in provenance['files']:assert sha(ROOT/item['path'])==item['sha256']
files=[x['path'] for x in provenance['files'] if x['path'].endswith('.v')]+[
    'rtl/backend/rv_fp_convert.sv','rtl/backend/rv_fp_round_to_int.sv','rtl/backend/rv_fp_immediate.sv',
    'rtl/backend/rv_fp_cvtmod.sv','tb/unit/backend/rv_fp_aux_tb.sv']
headers=[x['path'] for x in provenance['files'] if x['path'].endswith('.vi')]
with Simulator() as sim:
    model=sim.build('rva23_fp_aux','rv_fp_aux_tb',files,dependencies=headers)
    model['run']=sim.simulate(model,[f'+vectors={path.relative_to(ROOT).as_posix()}',f'+count={len(vectors)}'])
    model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'FP component datapaths; architectural integration pending',
        'model':model,'vectors':len(vectors),'vector_sha256':sha(path),
        'oracle_sha256':sha(ROOT/'scripts/fp_reference.py'),'generator_sha256':sha(__file__)})
    print('PASS FP auxiliary exact vectors',len(vectors),flush=True)

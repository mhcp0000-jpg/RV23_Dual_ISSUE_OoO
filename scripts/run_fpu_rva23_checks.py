"""F/D/Zfhmin/Zfa issue/result unit with real encodings and independent oracles."""
import json,random
from sim_runner import ROOT,Simulator,sha,dump
from fp_reference import BinaryFP
folder=ROOT/'out/rva23/fpu';folder.mkdir(parents=True,exist_ok=True)
mask64=(1<<64)-1
vectors=[]
def append(insn,a,b,c,result,flags,integer=False,frm=0,illegal=False):
    value=(insn<<352)|(a<<288)|(b<<224)|(c<<160)|(result<<96)|(flags<<91)|(frm<<88)|(integer<<87)|(illegal<<86)
    vectors.append(f'{value:096x}')
def boxed(value,width):return value|((mask64>>width)<<width)
for width in [32,64]:
    for line in (ROOT/f'out/rva23/fp_format/fp{width}.hex').read_text().splitlines():
        packed=int(line,16);insn=packed>>352
        a=(packed>>288)&mask64;b=(packed>>224)&mask64;c=(packed>>160)&mask64
        result=(packed>>96)&mask64;flags=(packed>>91)&31;rm=(packed>>88)&7
        family=insn>>27;is_op=insn&127==0x53
        integer=is_op and family in [20,24,28]
        int_source=is_op and family in [26,30]
        round_used=not is_op or family in [0,1,2,3,11,24,26]
        if round_used:
            dynamic=len(vectors)%2==0
            insn=(insn&~0x7000)|((7 if dynamic else rm)<<12)
        if width==32:
            if not int_source:a=boxed(a,32)
            b=boxed(b,32);c=boxed(c,32)
            if not integer:result=boxed(result,32)
        append(insn,a,b,c,result,flags,integer,rm)
for line in (ROOT/'out/rva23/fp_aux/vectors.hex').read_text().splitlines():
    packed=int(line,16);kind=packed>>380;fmt=(packed>>378)&3;src=(packed>>376)&3
    rm=(packed>>373)&7;nx=(packed>>372)&1;a=(packed>>288)&mask64
    result=(packed>>96)&mask64;flags=(packed>>91)&31
    integer=False
    if kind==0:
        if src==fmt:continue # same-format FCVT is reserved in the ISA
        insn=(8<<27)|(fmt<<25)|(src<<20)|(rm<<12)|(3<<7)|0x53
    elif kind==1:
        insn=(8<<27)|(fmt<<25)|((4+nx)<<20)|(rm<<12)|(3<<7)|0x53
        if fmt==0:a=boxed(a,32)
    elif kind==2:
        insn=(30<<27)|(fmt<<25)|(1<<20)|((a&31)<<15)|(3<<7)|0x53
    else:
        insn=(24<<27)|(1<<25)|(8<<20)|(1<<12)|(3<<7)|0x53
        integer=True;_,flags=BinaryFP(11,52).to_int(a,32,False,1)
    append(insn,a,0,0,result,flags,integer,rm)
# FMV.H.X / FMV.X.H do not require valid NaN boxing and never change flags.
rng=random.Random(0xF23A)
for _ in range(256):
    a=rng.getrandbits(64);low=a&65535
    append((30<<27)|(2<<25)|(3<<7)|0x53,a,0,0,boxed(low,16),0)
    append((28<<27)|(2<<25)|(3<<7)|0x53,a,0,0,(low|(~65535 if low&32768 else 0))&mask64,0,True)
# Invalid boxes are canonical quiet NaNs for arithmetic/classification, while
# moves preserve raw low bits. This catches use of the old 32-bit register path.
for a in [1,0x7f800001,0x80000000,0x12345678deadbeef]:
    append(0x001001d3,a,0xffffffff3f800000,0,0xffffffff7fc00000,0)
    append(0xe00011d3,a,0,0,512,0,True)
    low=a&0xffffffff;sign_extended=(low|(~0xffffffff if low>>31 else 0))&mask64
    append(0xe00001d3,a,0,0,sign_extended,0,True)
# Reserved formats/encodings and dynamic RM values must trap precisely.
for insn in [0x040001d3,0xe40011d3,0x000051d3,0x000061d3,
             0x5a1001d3,0xc24001d3,0x400001d3,0xf02001d3,0x040001c3]:
    append(insn,0,0,0,0,0,illegal=True)
for frm in [5,6,7]:append(0x000071d3,0xffffffff3f800000,0xffffffff3f800000,0,0,0,frm=frm,illegal=True)
path=folder/'vectors.hex';path.write_text('\n'.join(vectors)+'\n',encoding='utf-8')
assert len(vectors)<=65536,len(vectors)
provenance=json.loads((ROOT/'rtl/vendor/hardfloat/PROVENANCE.json').read_text())
files=['rtl/rv_ooo_pkg.sv','rtl/backend/rv_fp_decode_pkg.sv']+[
    x['path'] for x in provenance['files'] if x['path'].endswith('.v')]+[
    'rtl/backend/rv_fp_format.sv','rtl/backend/rv_fp_convert.sv','rtl/backend/rv_fp_round_to_int.sv',
    'rtl/backend/rv_fp_immediate.sv','rtl/backend/rv_fp_cvtmod.sv','rtl/backend/rv_fpu_rva23.sv',
    'tb/unit/backend/rv_fpu_rva23_tb.sv']
headers=[x['path'] for x in provenance['files'] if x['path'].endswith('.vi')]
with Simulator() as sim:
    model=sim.build('rva23_fpu','rv_fpu_rva23_tb',files,dependencies=headers)
    model['run']=sim.simulate(model,[f'+vectors={path.relative_to(ROOT).as_posix()}',f'+count={len(vectors)}'])
    model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'Scalar FP issue/result unit; full core integration pending',
        'model':model,'vectors':len(vectors),'vector_sha256':sha(path),'generator_sha256':sha(__file__),
        'oracle_sha256':sha(ROOT/'scripts/fp_reference.py')})
    print('PASS RVA23 FP issue/result exact vectors',len(vectors),flush=True)

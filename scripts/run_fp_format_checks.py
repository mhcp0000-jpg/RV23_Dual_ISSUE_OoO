"""Independent exact rational oracle + GNU encodings for HardFloat F/D RTL."""
import json,random,struct
from fractions import Fraction
from sim_runner import ROOT,Simulator,GCC,sha,dump
from fp_reference import BinaryFP
import gen_fpu_diff_vectors as previous
folder=ROOT/'out/rva23/fp_format';folder.mkdir(parents=True,exist_ok=True)
vendor=ROOT/'rtl/vendor/hardfloat'
provenance=json.loads((vendor/'PROVENANCE.json').read_text())
for item in provenance['files']:assert sha(ROOT/item['path'])==item['sha256']
files=[x['path'] for x in provenance['files'] if x['path'].endswith('.v')]+[
    'rtl/backend/rv_fp_format.sv','tb/unit/backend/rv_fp_format_tb.sv']
headers=[x['path'] for x in provenance['files'] if x['path'].endswith('.vi')]

def operations(suffix):
    result=[]
    for op in ['add','sub','mul','div']:
        result.append((op,f'f{op}.{suffix} ft3,ft0,ft1,rne'))
    for op in ['madd','msub','nmsub','nmadd']:
        result.append((op,f'f{op}.{suffix} ft3,ft0,ft1,ft2,rne'))
    result += [('sqrt',f'fsqrt.{suffix} ft3,ft0,rne')]
    for op in ['sgnj','sgnjn','sgnjx','min','max','minm','maxm']:
        result.append((op,f'f{op}.{suffix} ft3,ft0,ft1'))
    for op in ['eq','lt','le','ltq','leq']:
        result.append((op,f'f{op}.{suffix} t3,ft0,ft1'))
    for integer in ['w','wu','l','lu']:
        result += [('to_'+integer,f'fcvt.{integer}.{suffix} t3,ft0,rne'),
                   ('from_'+integer,f'fcvt.{suffix}.{integer} ft3,t0'+('' if suffix=='d' and integer in ['w','wu'] else ',rne'))]
    result += [('class',f'fclass.{suffix} t3,ft0'),
               ('move_to',f'fmv.x.{"d" if suffix=="d" else "w"} t3,ft0'),
               ('move_from',f'fmv.{"d" if suffix=="d" else "w"}.x ft3,t0')]
    return result

def expected(f,op,a,b,c,rm):
    a&=f.mask;b&=f.mask;c&=f.mask
    if op=='add':return f.add(a,b,rm)
    if op=='sub':return f.add(a,b,rm,True)
    if op=='mul':return f.multiply(a,b,rm)
    if op=='div':return f.divide(a,b,rm)
    if op in ['madd','msub','nmsub','nmadd']:return f.fused(a,b,c,rm,op in ['nmsub','nmadd'],op in ['msub','nmadd'])
    if op=='sqrt':return f.sqrt(a,rm)
    if op in ['min','max','minm','maxm']:return f.minmax(a,b,op in ['max','maxm'],op in ['minm','maxm'])
    if op in ['eq','lt','le','ltq','leq']:return f.compare(a,b,op[:-1] if op in ['ltq','leq'] else op,op in ['ltq','leq'])
    if op in ['sgnj','sgnjn','sgnjx']:
        sign=b&f.signbit
        if op=='sgnjn':sign^=f.signbit
        if op=='sgnjx':sign^=a&f.signbit
        return (a&~f.signbit)|sign,0
    if op.startswith('to_'):
        integer=op[3:];bits=64 if integer.startswith('l') else 32
        value,flags=f.to_int(a,bits,integer.endswith('u'),rm)
        value&=(1<<bits)-1
        if bits==32 and value>>31:value|=0xffffffff00000000
        return value,flags
    if op.startswith('from_'):
        integer=op[5:];return f.from_int(a,64 if integer.startswith('l') else 32,integer.endswith('u'),rm)
    if op=='class':return f.classify(a),0
    if op=='move_to':return ((a|(~f.mask)) if f.sign(a) else a)&((1<<64)-1),0
    if op=='move_from':return a,0
    raise ValueError(op)

# Compare generic binary32 arithmetic to the previous independent regression
# oracle before using the new format oracle for FP64.
rng=random.Random(0xF2364);f32=BinaryFP(8,23)
for _ in range(1000):
    a,b,c=[rng.getrandbits(32) for _ in range(3)];rm=rng.randrange(5)
    for op,oldop in [('add',previous.OP_ADD),('sub',previous.OP_SUB),('mul',previous.OP_MUL),
        ('div',previous.OP_DIV),('sqrt',previous.OP_SQRT),('madd',previous.OP_FMADD)]:
        new=expected(f32,op,a,b,c,rm);old=previous.execute(oldop,rm,a,b,c)
        if new!=old:
            assert new[0]==old[0] and new[1]==(old[1]|2) and new[0]&0x7fffffff==0x00800000,(op,a,b,c,rm,new,old)
assert f32.fused(0x00800001,0x3f7fffff,1,3,False,True)==(0x00800000,3)

report={'passed':False,'scope':'F/D arithmetic component; FP64 architectural state/core integration remains pending',
    'oracle_sha256':sha(ROOT/'scripts/fp_reference.py'),'vendor_provenance_sha256':sha(vendor/'PROVENANCE.json'),'cases':[]}
with Simulator() as sim:
    for width in [32,64]:
        f=BinaryFP(8,23) if width==32 else BinaryFP(11,52)
        suffix='s' if width==32 else 'd';ops=operations(suffix)
        source=folder/f'fp{width}.S';obj=folder/f'fp{width}.o';binary=folder/f'fp{width}.bin'
        source.write_text('.text\n.option norvc\n'+'\n'.join(x[1] for x in ops)+'\n',encoding='utf-8')
        sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imafd_zfa','-mabi=lp64d','-c',source,'-o',obj],folder/f'fp{width}_assemble.log',60)
        sim.run([GCC/'riscv-none-elf-objcopy.exe','-O','binary','-j','.text',obj,binary],folder/f'fp{width}_objcopy.log',60)
        code=binary.read_bytes();assert len(code)==4*len(ops)
        one=f.bias<<f.fb
        specials=[0,f.signbit,1,f.signbit|1,f.fracmask,1<<f.fb,one,one|f.signbit,
            one-1,one+1,f.inf-1,f.inf,f.inf|f.signbit,f.nan,f.nan|1,f.inf|1,
            f.mask,(1<<f.fb)|1,(one+(2<<f.fb))|f.signbit]
        vectors=[]
        for index,(op,_) in enumerate(ops):
            insn=struct.unpack_from('<I',code,index*4)[0]
            for rm in range(5):
                operands=[(a,specials[(i*7+3)%len(specials)],specials[(i*11+5)%len(specials)]) for i,a in enumerate(specials)]
                operands += [(rng.getrandbits(width),rng.getrandbits(width),rng.getrandbits(width)) for _ in range(80)]
                # Integer conversions additionally exercise all 64 source bits.
                if op.startswith('from_'):operands += [(x,0,0) for x in [0,1,(1<<63)-1,1<<63,(1<<64)-1,0x80000000]]
                for a,b,c in operands:
                    # Preserve full XLEN for FCVT from L/LU, regardless of FP format.
                    if op.startswith('from_'):
                        integer=op[5:];value,flags=f.from_int(a,64 if integer.startswith('l') else 32,integer.endswith('u'),rm)
                    else:value,flags=expected(f,op,a,b,c,rm)
                    packed=(insn<<352)|(a<<288)|(b<<224)|(c<<160)|(value<<96)|(flags<<91)|(rm<<88)|((op in ['div','sqrt'])<<87)
                    vectors.append(f'{packed:096x}')
        path=folder/f'fp{width}.hex';path.write_text('\n'.join(vectors)+'\n',encoding='utf-8')
        model=sim.build(f'rva23_fp_format_{width}','rv_fp_format_tb',files,[f'-GWIDTH={width}'],dependencies=headers)
        model['run']=sim.simulate(model,[f'+vectors={path.relative_to(ROOT).as_posix()}',f'+count={len(vectors)}'])
        model['passed']=True
        report['cases'].append({'width':width,'vectors':len(vectors),'vector_sha256':sha(path),'model':model})
        dump(folder/'report.json',report);print('PASS FP format',width,'exact vectors',len(vectors),flush=True)
    report['passed']=True;dump(folder/'report.json',report)

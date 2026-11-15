"""FP instruction streams through the vector owner: masks, restart and flags."""
import json,struct
from sim_runner import ROOT,Simulator,GCC,sha,dump
from fp_reference import BinaryFP
folder=ROOT/'out/rva23/vector_fp_engine';folder.mkdir(parents=True,exist_ok=True)
mask=(1<<64)-1;program=[];f32=BinaryFP(8,23);f64=BinaryFP(11,52)
def op(text,a=0,b=0,value=0,flags=0,illegal=False,frm=0,fs=1):
    program.append((0,text,a&mask,b&mask,value&mask,int(illegal),2,flags,frm,fs))
def csr(address,value):program.append((1,f'.word {address}',value,0,0,0,2,0,0,1))
def config(vl,width,lmul='m1',actual=None):
    op(f'vsetivli a2,{vl},e{width},{lmul},tu,mu',value=vl if actual is None else actual)
def elements(reg,values,width):
    for i,value in enumerate(values):
        op(f'vslidedown.vi v24,v{reg},{i}')
        op('vmv.x.s a1,v24',value=value-(1<<width) if value>>(width-1) else value)
def floats(values,f=f32):return [f.pack(x,0)[0] for x in values]
def boxed(value):return 0xffffffff00000000|value

config(4,32)
op('vmv.v.x v1,a0',a=0x3f800000)
op('vid.v v2');op('vfcvt.f.x.v v2,v2');elements(2,floats([0,1,2,3]),32)
op('vfadd.vv v4,v1,v2');elements(4,floats([1,2,3,4]),32)
op('vfadd.vf v5,v2,fa0',a=boxed(0x40000000));elements(5,floats([2,3,4,5]),32)
op('vmfeq.vf v0,v2,fa0',a=boxed(0x40000000))
op('vmv.v.x v6,a0',a=0xbf800000)
op('vfdiv.vv v6,v1,v2,v0.t');elements(6,[0xbf800000,0xbf800000,0x3f000000,0xbf800000],32)
op('vfdiv.vv v7,v1,v2',flags=9);elements(7,[0x7f800000,0x3f800000,0x3f000000,0x3eaaaaab],32)
op('vfredosum.vs v8,v2,v1');op('vmv.x.s a1,v8',value=0x40e00000)
op('vfredmin.vs v8,v2,v1');op('vmv.x.s a1,v8',value=0)
op('vfredmax.vs v8,v2,v1');op('vmv.x.s a1,v8',value=0x40400000)
op('vmv.v.x v9,a0',a=0x7f800001)
op('vmv.v.i v0,0')
op('vfredosum.vs v10,v2,v9,v0.t');op('vmv.x.s a1,v10',value=0x7f800001)
op('vfredusum.vs v10,v2,v9,v0.t');op('vmv.x.s a1,v10',value=0x7f800001)
op('vmv.v.i v0,-1')
op('vfredosum.vs v10,v2,v9,v0.t',flags=16);op('vmv.x.s a1,v10',value=0x7fc00000)
config(2,64);op('vmv.s.x v11,a0',a=0x3ff0000000000000)
config(4,32);op('vfwredosum.vs v12,v2,v11')
config(2,64);op('vmv.x.s a1,v12',value=0x401c000000000000)
config(4,32);op('vfwadd.vv v16,v1,v2')
config(4,64,'m2');elements(16,floats([1,2,3,4],f64),64)
config(4,32)
op('vfmv.f.s fa0,v1',value=boxed(0x3f800000))
op('vmv.v.x v13,a0',a=0x40400000)
config(0,32)
op('vfmv.f.s fa0,v1',value=boxed(0x3f800000))
op('vfmv.s.f v13,fa0',a=boxed(0x40000000))
op('vfdiv.vv v7,v1,v0') # probe's dummy 0/0 NV must not become architectural
op('vfadd.vv v7,v1,v2',illegal=True,frm=6)
op('vfadd.vv v7,v1,v2',illegal=True,fs=0)
config(4,32);op('vmv.x.s a1,v13',value=0x40400000)
op('vmfeq.vv v0,v2,v1') # lane 1 only
op('vfmerge.vfm v14,v2,fa0,v0',a=boxed(0x41100000));elements(14,floats([0,9,2,3]),32)
op('vfslide1up.vf v14,v2,fa0',a=boxed(0x41100000));elements(14,floats([9,0,1,2]),32)
op('vfslide1down.vf v14,v2,fa0',a=boxed(0x41100000));elements(14,floats([1,2,3,9]),32)
op('vmv.v.x v14,a0',a=0x7f800001)
op('vfslide1up.vf v15,v14,fa0',a=boxed(0x3f800000));elements(15,[0x3f800000]+[0x7f800001]*3,32)
config(8,16)
op('vid.v v16');op('vfwcvt.f.x.v v18,v16') # I16 -> F32 is required by V
config(8,32,'m2');elements(18,floats(range(8)),32)
config(8,16);op('vfncvt.x.f.w v20,v18');elements(20,list(range(8)),16)
op('vfncvt.f.f.w v22,v18');elements(22,[0,0x3c00,0x4000,0x4200,0x4400,0x4500,0x4600,0x4700],16)
op('vfwcvt.f.f.v v26,v22')
config(8,32,'m2');elements(26,floats(range(8)),32)
config(2,64);op('vmv.v.x v4,a0',a=0x3ff0000000400000)
config(2,32,'mf2');op('vfncvt.rod.f.f.w v6,v4',flags=1);elements(6,[0x3f800001]*2,32)
config(4,32);op('vmv.v.x v7,a0',a=0xbf800000);csr(0x008,2)
op('vfadd.vv v7,v1,v2');elements(7,[0xbf800000,0xbf800000,0x40400000,0x40800000],32)
op('vid.v v14',fs=0);elements(14,list(range(4)),32)
config(0,16);op('vfadd.vv v7,v1,v2',illegal=True) # illegal context even for VL=0

source=folder/'program.S';source.write_text('.text\n.option norvc\n'+'\n'.join(row[1] for row in program)+'\n')
model=json.loads((ROOT/'out/rva23/vector_integer_engine/report.json').read_text())['model']
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
with Simulator() as sim:
    obj=folder/'program.o';binary=folder/'program.bin'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcv_zvbb_zvfhmin','-mabi=lp64d','-c',source,'-o',obj],folder/'assemble.log',60)
    sim.run([GCC/'riscv-none-elf-objcopy.exe','-O','binary','-j','.text',obj,binary],folder/'objcopy.log',60)
    data=binary.read_bytes();assert len(data)==4*len(program)
    vectors=folder/'program.hex'
    vectors.write_text('\n'.join(f'{kind:x} {struct.unpack_from("<I",data,i*4)[0]:08x} {a:016x} {b:016x} {value:016x} {illegal:x} {sat:x} {flags:02x} {frm:x} {fs:x}'
        for i,(kind,asm,a,b,value,illegal,sat,flags,frm,fs) in enumerate(program))+'\n')
    model['run']=sim.simulate(model,[f'+vectors={vectors.relative_to(ROOT).as_posix()}'],label='vector_fp')
    fresh();model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'Vector integer+FP development owner, masks/restart/flags; memory and core integration missing',
        'instructions':len(program),'model':model,'generator_sha256':sha(__file__),'source_sha256':sha(source),'vectors_sha256':sha(vectors)})
    print('PASS vector FP owner packets',len(program),'mask/restart/flags/half conversions; native core integration has separate evidence',flush=True)

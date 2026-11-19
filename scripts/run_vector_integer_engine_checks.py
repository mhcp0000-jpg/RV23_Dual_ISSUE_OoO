"""GNU instruction stream through configuration, snapshots, masks and element math.

This standalone owner test does not establish core integration by itself.
Native execution, FP and memory have separate directed streams.
"""
import json,struct
from sim_runner import ROOT,Simulator,GCC,sha,dump
from vector_integer_reference import rounded
folder=ROOT/'out/rva23/vector_integer_engine';folder.mkdir(parents=True,exist_ok=True)
program=[];mask=(1<<64)-1
def op(assembly,a=0,b=0,expected=0,exception=False,sat=2):
    program.append([0,assembly,a&mask,b&mask,expected&mask,int(exception),sat])
def csr(address,value,sat=2):program.append([1,f'.word {address}',value,0,0,0,sat])
def elements(reg,values,width):
    for index,value in enumerate(values):
        op(f'vslidedown.vi v24,v{reg},{index}')
        signed=value-(1<<width) if value>>(width-1) else value
        op('vmv.x.s a1,v24',expected=signed)

op('vsetivli a2,16,e8,m1,tu,mu',expected=16)
op('vmv.v.i v1,9');op('vadd.vi v2,v1,3');elements(2,[12]*16,8)
op('vadd.vx v3,v2,a0',a=-18);elements(3,[250]*16,8)
op('vsaddu.vx v4,v3,a0',a=27,sat=1);elements(4,[255]*16,8)
op('vid.v v8');elements(8,list(range(16)),8)
op('vmseq.vi v0,v8,3');op('vmv.v.x v9,a0',a=170)
op('vadd.vi v9,v8,15,v0.t');elements(9,[18 if i==3 else 170 for i in range(16)],8)
op('vmv.v.x v10,a0',a=170);op('vcompress.vm v10,v8,v0');elements(10,[3]+[170]*15,8)
op('vfirst.m a1,v0',expected=3);op('vcpop.m a1,v0',expected=1)
op('vmsbf.m v11,v0');op('vcpop.m a1,v11',expected=3)
op('vmsif.m v11,v0');op('vcpop.m a1,v11',expected=4)
op('vmsof.m v11,v0');op('vcpop.m a1,v11',expected=1)
op('viota.m v12,v0');elements(12,[0]*4+[1]*12,8)
op('vredsum.vs v13,v8,v1');op('vmv.x.s a1,v13',expected=-127)
op('vwredsumu.vs v14,v8,v1')
op('vsetivli a2,8,e16,m1,tu,mu',expected=8);op('vmv.x.s a1,v14',expected=0x981)
op('vmv.s.x v1,a0',a=9)
op('vsetivli a2,16,e8,m1,tu,mu',expected=16);op('vwredsumu.vs v14,v8,v1')
op('vsetivli a2,8,e16,m1,tu,mu',expected=8);op('vmv.x.s a1,v14',expected=129)
op('vsetivli a2,16,e8,m1,tu,mu',expected=16)
op('vwaddu.vx v16,v8,a0',a=254)
op('vsetivli a2,16,e16,m2,tu,mu',expected=16);elements(16,list(range(254,270)),16)
op('vsetivli a2,16,e8,m1,tu,mu',expected=16)
for rm in range(4):
    csr(0x00f,rm<<1,sat=0)
    op('vnclipu.wi v20,v16,1');elements(20,[rounded(x,1,rm) for x in range(254,270)],8)
op('vrgather.vv v18,v8,v8');elements(18,list(range(16)),8)
op('vrgather.vx v18,v8,a0',a=999);elements(18,[0]*16,8)
op('vslide1up.vx v18,v8,a0',a=99);elements(18,[99]+list(range(15)),8)
op('vslide1down.vx v18,v8,a0',a=99);elements(18,list(range(1,16))+[99],8)
op('vbrev.v v18,v8');elements(18,[int(f'{i:08b}'[::-1],2) for i in range(16)],8)
csr(0x008,5)
op('viota.m v12,v0',exception=True)
op('vadd.vi v3,v8,1');elements(3,[250]*5+list(range(6,17)),8)
op('vredsum.vs v0,v8,v1,v0.t');op('vmv.x.s a1,v0',expected=12)
# Whole-register moves remain usable while vtype.vill is set and vl is zero.
op('vsetvl a2,a0,a1',a=16,b=-1,expected=0)
op('vmv2r.v v16,v8')
op('vsetivli a2,31,e8,m2,tu,mu',expected=31)
elements(16,list(range(16))+[18 if i==3 else 170 for i in range(15)],8)
op('vsetivli a2,31,e8,mf8,tu,mu',expected=2)
op('vid.v v29');op('vadd.vi v30,v29,9');elements(30,[9,10],8)
op('vwaddu.vx v31,v29,a0',a=255)
op('vsetivli a2,31,e16,mf4,tu,mu',expected=2);elements(31,[255,256],16)
op('vsetvl a2,a0,a1',a=-1,b=3,expected=128) # LMUL8, largest implemented VL
op('vid.v v8')
for index in [0,31,63,100,127]:
    op('vslidedown.vx v24,v8,a0',a=index);op('vmv.x.s a1,v24',expected=index)
csr(0x008,127)
op('vadd.vi v16,v8,1')
op('vslidedown.vx v24,v16,a0',a=127);op('vmv.x.s a1,v24',expected=-128)
op('vcpop.v v16,v8')
for index in [0,31,127]:
    op('vslidedown.vx v24,v16,a0',a=index);op('vmv.x.s a1,v24',expected=index.bit_count())
op('vcpop.v v16,v9',exception=True) # LMUL8 source group must start on an 8-register boundary
# Mixed-width source groups must not share a register, even at different
# offsets within the groups. Same-width source aliases remain legal.
op('vsetivli a2,4,e16,m1,tu,mu',expected=4)
op('vmv.v.i v10,2')
op('vmv.v.i v11,3')
op('vadd.vv v20,v10,v10')
elements(20,[4]*4,16)
op('vwaddu.wv v16,v8,v9',exception=True)
op('vnsrl.wv v20,v8,v9',exception=True)
op('vwaddu.wv v16,v8,v11')
op('vnsrl.wv v20,v8,v11')
op('vsetivli a2,4,e8,m1,tu,mu',expected=4)
op('vrgatherei16.vv v20,v9,v8',exception=True)
op('vrgatherei16.vv v20,v11,v8')
op('vsetvl a2,a0,a1',a=-1,b=3,expected=128)
# Reserved group alignment, unsupported SEW8 FP and non-SRAM memory fault.
op('vwaddu.vx v17,v8,a0',exception=True)
op('vfadd.vv v8,v16,v24',exception=True)
op('vle8.v v8,(a0)',exception=True)

# This implementation preserves mask tails and inactive bits. Observe all 128
# bits, including those above VLMAX, using two scalar reads at SEW=64.
def mask_words(reg, low, high):
    op('vsetivli a2,2,e64,m1,tu,mu',expected=2)
    op(f'vmv.x.s a1,v{reg}',expected=low)
    op(f'vslidedown.vi v24,v{reg},1')
    op('vmv.x.s a1,v24',expected=high)

for policy in ['tu,mu', 'tu,ma', 'ta,mu', 'ta,ma']:
    initial = 0xa5a5a5a5a5a5a5f0
    op('vsetivli a2,2,e64,m1,tu,mu',expected=2)
    op('vmv.v.x v7,a0',a=initial)
    op('vmv.s.x v0,a0',a=0x55)
    op(f'vsetivli a2,7,e8,m1,{policy}',expected=7)
    csr(0x008,2)
    op('vmsltu.vx v7,v8,a0,v0.t',a=4)
    # Active indices are 2, 4 and 6. Only index 2 compares true.
    mask_words(7, (initial & ~0x54) | 0x04, initial)

    op(f'vsetivli a2,0,e8,m1,{policy}',expected=0)
    op('vmseq.vi v7,v8,0')
    mask_words(7, (initial & ~0x54) | 0x04, initial)
    op(f'vsetivli a2,7,e8,m1,{policy}',expected=7)
    csr(0x008,7)
    op('vmseq.vi v7,v8,0')
    mask_words(7, (initial & ~0x54) | 0x04, initial)

# LMUL8 supplies eight consecutive 128-bit batches at every SEW.
for size in range(4):
    width=8<<size;length=128>>size
    op('vsetvl a2,a0,a1',a=length,b=(size<<3)|3,expected=length)
    op('vmv.v.i v16,2');op('vmv.v.i v24,3');op('vadd.vv v8,v16,v24')
    for index in sorted({0,1,(64//width)-1,64//width,(128//width)-1,128//width,length//2,length-1}):
        op('vslidedown.vx v0,v8,a0',a=index)
        op('vmv.x.s a1,v0',expected=5)

source=folder/'program.S';source.write_text('.text\n.option norvc\n'+'\n'.join(row[1] for row in program)+'\n')
with Simulator() as sim:
    obj=folder/'program.o';binary=folder/'program.bin'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcv_zvbb','-mabi=lp64d','-c',source,'-o',obj],folder/'assemble.log',60)
    sim.run([GCC/'riscv-none-elf-objcopy.exe','-O','binary','-j','.text',obj,binary],folder/'objcopy.log',60)
    data=binary.read_bytes();assert len(data)==4*len(program)
    vectors=folder/'program.hex'
    vectors.write_text('\n'.join(f'{kind:x} {struct.unpack_from("<I",data,i*4)[0]:08x} {a:016x} {b:016x} {value:016x} {exception:x} {sat:x} 00 0 1'
        for i,(kind,asm,a,b,value,exception,sat) in enumerate(program))+'\n')
    vendor=json.loads((ROOT/'rtl/vendor/hardfloat/PROVENANCE.json').read_text())
    files=['rtl/rv_ooo_pkg.sv','rtl/backend/rv_fp_decode_pkg.sv','rtl/backend/rv_vector_decode_pkg.sv',
        'rtl/backend/rv_vector_estimate_tables_pkg.sv']+[
        x['path'] for x in vendor['files'] if x['path'].endswith('.v')]+[
        'rtl/backend/'+name+'.sv' for name in ['rv_fp_format','rv_fp_convert','rv_fp_round_to_int',
        'rv_fp_immediate','rv_fp_cvtmod','rv_fpu_rva23','rv_vector_fp_integer','rv_vector_fp_estimate',
        'rv_divider','rv_vector_divider','rv_vector_fp_lane','rv_vector_integer_alu','rv_vector_simd_alu','rv_vector_config','rv_vector_register_file','rv_vector_engine']]+[
        'rtl/backend/rv_pmp.sv','rtl/soc/rv23_pointer_mask.sv','rtl/backend/rv23_hypervisor_memory_head.sv',
        'tb/unit/backend/rv_vector_integer_engine_tb.sv']
    model=sim.build('rva23_vector_integer_engine','rv_vector_integer_engine_tb',files)
    model['run']=sim.simulate(model,[f'+vectors={vectors.relative_to(ROOT).as_posix()}']);model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'Integer instruction stream through development vector owner; memory/native integration has separate evidence',
        'instructions':len(program),'model':model,'source_sha256':sha(source),'vectors_sha256':sha(vectors),
        'generator_sha256':sha(__file__),'oracle_sha256':sha(ROOT/'scripts/vector_integer_reference.py')})
    print('PASS integer vector owner stream',len(program),'operations; complete architectural verification remains separate',flush=True)

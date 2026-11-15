"""Every C.FLD/FSD/FLDSP/FSDSP encoding against GNU canonical instructions."""
import struct
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/compressed_d';folder.mkdir(parents=True,exist_ok=True)
pairs=[]
for a in range(8,16):
    for b in range(8,16):
        for offset in range(0,256,8):
            for c,op in [('fld','fld'),('fsd','fsd')]:
                pairs.append((f'c.{c} f{a},{offset}(x{b})',f'{op} f{a},{offset}(x{b})'))
for a in range(32):
    for offset in range(0,512,8):
        for c,op in [('fldsp','fld'),('fsdsp','fsd')]:
            pairs.append((f'c.{c} f{a},{offset}(sp)',f'{op} f{a},{offset}(sp)'))
assert len(pairs)==8192
source=folder/'test.S';obj=source.with_suffix('.o');raw=source.with_suffix('.bin')
source.write_text('.text\n'+''.join(f'.option rvc\n{a}\n.option norvc\n{b}\n' for a,b in pairs))
with Simulator() as sim:
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imafdc','-mabi=lp64d','-c',source,'-o',obj],folder/'assemble.log',60)
    sim.run([GCC/'riscv-none-elf-objcopy.exe','-O','binary','-j','.text',obj,raw],folder/'objcopy.log',60)
    data=raw.read_bytes();assert len(data)==6*len(pairs)
    vector=folder/'vectors.hex'
    vector.write_text(''.join(f'{struct.unpack_from("<I",data,i+2)[0]:08x}{struct.unpack_from("<H",data,i)[0]:04x}\n'
        for i in range(0,len(data),6)))
    model=sim.build('rva23_compressed_d','rv_compressed_profile_tb',[
        'rtl/frontend/rv_c_expander.sv','tb/unit/backend/rv_compressed_profile_tb.sv'],[
        '-GXLEN=64','-GHAS_D=1',f'-GCASES={len(pairs)}',f'-GVECTOR_FILE="{vector.relative_to(ROOT).as_posix()}"'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(folder/'report.json',{'passed':True,'model':model,'encodings':len(pairs),
        'generator_sha256':sha(__file__),'vectors_sha256':sha(vector),'assembly_sha256':sha(source)})
    print('PASS all 8192 compressed D encodings; all 65536 compressed instructions checked',flush=True)

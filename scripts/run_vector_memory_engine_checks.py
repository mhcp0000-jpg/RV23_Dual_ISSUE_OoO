"""GNU vector memory stream, independent byte memory oracle and precise restart."""
import json,struct,random
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/vector_memory_engine';folder.mkdir(parents=True,exist_ok=True)
program=[];mask=(1<<64)-1;base=0x80000000
memory=bytearray((i*37+11)&255 for i in range(1048576))
accesses=0;current_width=8
def packet(kind,asm='.word 0',a=0,b=0,value=0,exc=0,cause=0,tval=0):
    program.append([kind,asm,a&mask,b&mask,value&mask,exc,cause,tval])
def op(asm,a=0,b=0,value=0,cause=0,tval=None):
    packet(0,asm,a,b,value,int(bool(cause)),cause,tval)
def csr(address,value):packet(1,f'.word {address}',a=value)
def state(vl,start=0):packet(4,a=vl,b=start)
def traffic():packet(5,a=accesses)
def config(vl,width,lmul='m1'):
    global current_width
    current_width=width
    op(f'vsetvli a2,a0,e{width},{lmul},tu,mu',a=vl,value=vl)
def elements(reg,values,width=None):
    width=width or current_width
    for i,value in enumerate(values):
        op(f'vslidedown.vx v24,v{reg},a0',a=i)
        signed=value-(1<<width) if value>>(width-1) else value
        op('vmv.x.s a1,v24',value=signed)
def raw(address,size):
    return int.from_bytes(memory[address-base:address-base+size],'little')
def verify(address,length):
    for i in range(length):packet(3,a=address+i,value=memory[address-base+i])
def write_ref(address,value,size):memory[address-base:address-base+size]=value.to_bytes(size,'little')
def load(asm,address,count,size,reg=8,stride=None,offsets=None,fields=1,start=0,active=None):
    global accesses
    op(asm,a=address,b=stride or 0)
    values=[[] for _ in range(fields)]
    for i in range(count):
        for field in range(fields):
            at=address+(offsets[i] if offsets is not None else i*(stride if stride is not None else fields*size))+field*size
            values[field].append(raw(at,size))
            if i>=start and (active is None or active[i]):accesses+=size
    return values

# All ordinary EEWs: misaligned, bank/line/page boundaries, held physical bus.
for width in [8,16,32,64]:
    size=width//8;count=128//width
    for offset in [7,61,4093]:
        config(count,width)
        values=load(f'vle{width}.v v8,(a0)',base+offset,count,size)[0]
        elements(8,values,width)
        target=base+0x8000+offset
        op(f'vse{width}.v v8,(a0)',a=target)
        for i,value in enumerate(values):write_ref(target+i*size,value,size)
        accesses+=count*size;verify(target-1,count*size+2)
traffic()
# Negative and zero byte strides, including data repetition with rs2!=x0.
for width in [8,16,32,64]:
    size=width//8;count=128//width
    for stride in [-size*3,0,size*5]:
        config(count,width)
        values=load(f'vlse{width}.v v8,(a0),a1',base+0x1200,count,size,stride=stride)[0]
        elements(8,values,width)
        target=base+0x9000
        op(f'vsse{width}.v v8,(a0),a1',a=target,b=stride)
        for i,value in enumerate(values):write_ref(target+i*stride,value,size)
        accesses+=count*size;verify(target-128,256)
traffic()
# Unit/strided segments, fields stored in independently aligned register groups.
for fields in [2,3,4,8]:
    for stride in [None,-17]:
        config(4,32)
        mnemonic=f'vlseg{fields}e32.v v8,(a0)' if stride is None else f'vlsseg{fields}e32.v v8,(a0),a1'
        values=load(mnemonic,base+0x2003,4,4,fields=fields,stride=stride)
        for field in range(fields):elements(8+field,values[field],32)
        target=base+0xa003
        mnemonic=f'vsseg{fields}e32.v v8,(a0)' if stride is None else f'vssseg{fields}e32.v v8,(a0),a1'
        op(mnemonic,a=target,b=stride or 0)
        for i in range(4):
            for field in range(fields):write_ref(target+i*(stride if stride is not None else fields*4)+field*4,values[field][i],4)
        accesses+=fields*4*4;verify(target-64,256)
traffic()
# Encoded EEW differs from SEW: EMUL both fractional and widened.
config(4,32)
values=load('vle8.v v8,(a0)',base+0x3101,4,1)[0]
config(4,8,'mf4');elements(8,values,8)
config(16,8)
values=load('vle64.v v8,(a0)',base+0x3201,16,8)[0]
config(16,64,'m8');elements(8,values,64)
traffic()
# Indexed source EEW8/16/32/64, zero extension, ordered and unordered variants.
for index_width in [8,16,32,64]:
    count=2;offsets=[0,1<<(index_width-1)] if index_width==8 else [0,37]
    config(count,index_width)
    for i,value in enumerate(reversed(offsets)):
        op('vslide1up.vx v1,v1,a0',a=value) # reserved overlap: use alternate destination below
        # Replace with legal alternating source/destination registers.
        program[-1][1]=f'vslide1up.vx v{1+i%2},v{2-i%2},a0'
    index_reg=2
    config(count,32)
    for ordered in [False,True]:
        mnemonic='vloxei' if ordered else 'vluxei'
        values=load(f'{mnemonic}{index_width}.v v8,(a0),v{index_reg}',base+0x4003,count,4,offsets=offsets)[0]
        elements(8,values,32)
        target=base+0xb003
        mnemonic='vsoxei' if ordered else 'vsuxei'
        op(f'{mnemonic}{index_width}.v v8,(a0),v{index_reg}',a=target)
        for i,value in enumerate(values):write_ref(target+offsets[i],value,4)
        accesses+=count*4;verify(target,offsets[-1]+4)
traffic()
# Segmented indexed loads forbid destination/index overlap and restart fields.
config(4,32);op('vid.v v1');op('vsll.vi v1,v1,4')
values=load('vluxseg3ei32.v v8,(a0),v1',base+0x5001,4,4,fields=3,offsets=[0,16,32,48])
for field in range(3):elements(8+field,values[field],32)
op('vluxseg3ei32.v v1,(a0),v1',a=base,cause=2)
traffic()
# Masked loads/stores must not check addresses or touch masked-off elements.
config(16,8);op('vid.v v1');op('vmsltu.vi v0,v1,5');op('vmv.v.i v8,-1')
address=base+0xffffb
values=load('vle8.v v8,(a0),v0.t',address,5,1)[0]
elements(8,values+[255]*11,8)
op('vse8.v v8,(a0),v0.t',a=address)
accesses+=5
for i,value in enumerate(values):write_ref(address+i,value,1)
verify(address,5);traffic()
op('vmseq.vx v0,v1,a0',a=31) # all elements masked off, invalid base must not fault
op('vle64.v v8,(a0),v0.t',a=0);op('vse64.v v8,(a0),v0.t',a=0);traffic()
# Mask stores from v0 are legal. Mask loads use ceil(vl/8) bytes, byte vstart.
config(13,8);op('vlm.v v0,(a0)',a=base+0x6001);accesses+=2
op('vsm.v v0,(a0)',a=base+0xc001);accesses+=2
for i in range(2):write_ref(base+0xc001+i,raw(base+0x6001+i,1),1)
verify(base+0xc001,2);traffic()
csr(8,1);op('vlm.v v8,(a0)',a=base+0x6101);accesses+=1;state(13)
config(2,8);op('vslidedown.vi v24,v8,1');op('vmv.x.s a1,v24',value=raw(base+0x6102,1)-(256 if raw(base+0x6102,1)>127 else 0))
# Whole registers ignore vill/vl and honor their own encoded EEW and vstart.
op('vsetvl a2,a0,a1',a=0,b=-1,value=0)
op('vl8re64.v v8,(a0)',a=base+0x7003);accesses+=128
op('vs8r.v v8,(a0)',a=base+0xd003);accesses+=128
for i in range(128):write_ref(base+0xd003+i,raw(base+0x7003+i,1),1)
verify(base+0xd002,130);traffic()
csr(8,127);op('vs8r.v v8,(a0)',a=base+0xe003);accesses+=1
write_ref(base+0xe003+127,raw(base+0x7003+127,1),1)
verify(base+0xe003,128);state(0);traffic()
# Precise split-element faults: no partial write before all bytes pass PMA.
config(4,32);op('vmv.v.i v8,7')
op('vse32.v v8,(a0)',a=base+0xffffa,cause=7,tval=base+0x100000)
accesses+=4;write_ref(base+0xffffa,7,4);state(4,1);verify(base+0xffffa,6);traffic()
# Retry at vstart1 writes only remaining elements at a repaired base.
op('vse32.v v8,(a0)',a=base+0xf000)
for i in range(1,4):write_ref(base+0xf000+i*4,7,4)
accesses+=12;verify(base+0xf000,16);state(4);traffic()
# Load fault preserves destination element and subsequent elements, then replay.
op('vle32.v v8,(a0)',a=base+0xffffa,cause=5,tval=base+0x100000)
accesses+=4;state(4,1)
csr(8,0);elements(8,[raw(base+0xffffa,4),7,7,7],32)
csr(8,1);op('vle32.v v8,(a0)',a=base+0xf000);accesses+=12
elements(8,[raw(base+0xffffa,4),7,7,7],32);state(4);traffic()
# Fault-only-first traps at element0, trims vl after later faults.
op('vle32ff.v v8,(a0)',a=base+0xffffa);accesses+=4;state(1);traffic()
config(4,32);op('vle32ff.v v8,(a0)',a=base+0xfffff,cause=5,tval=base+0x100000);state(4,0);traffic()
# Segment element0 can retain completed first field while reporting vstart0.
op('vlseg2e32ff.v v8,(a0)',a=base+0xffffc,cause=5,tval=base+0x100000);accesses+=4;state(4,0);traffic()
# Ordinary load/store vstart>=vl must issue no memory requests.
csr(8,4);op('vle32.v v8,(a0)',a=0);state(4);traffic()
csr(8,7);op('vse32.v v8,(a0)',a=0);state(4);traffic()
# Context-invalid group encodings remain illegal even when vl=0.
config(0,8);op('vle64.v v9,(a0)',a=base,cause=2);traffic()

# Sv39: adjacent VAs mapped onto nonadjacent SRAM pages, with per-byte
# translation/prevalidation and architectural vector-element restart.
def pte(address,value):
    packet(7,a=address,b=value);write_ref(address,value,8)
root=base+0x10000;l1=root+4096;l0=l1+4096
for at in range(root,l0+4096,8):pte(at,0)
pte(root+8,((l1>>12)<<10)|1)
pte(l1,((l0>>12)<<10)|1)
pa1=base+0x20000;pa2=base+0x30000;va=0x40003000
pte(l0+3*8,((pa1>>12)<<10)|0xc7)
def second(flags=0xc7,extra=0):
    pte(l0+4*8,((pa2>>12)<<10)|flags|extra)
    packet(8)
second()
packet(6,'.word 1',a=(8<<60)|(root>>12),b=1<<62)
config(4,64,'m2')
address=va+0xff4
def virtual_value(index,size=8):
    data=[]
    for byte in range(size):
        offset=0xff4+index*size+byte
        at=(pa1+offset) if offset<4096 else pa2+offset-4096
        data.append(raw(at,1))
    return int.from_bytes(bytes(data),'little')
values=[virtual_value(i) for i in range(4)]
op('vle64.v v8,(a0)',a=address);accesses+=32;elements(8,values,64)
op('vadd.vi v8,v8,1');values=[(x+1)&mask for x in values]
op('vse64.v v8,(a0)',a=address);accesses+=32
for i,value in enumerate(values):
    for byte in range(8):
        offset=0xff4+i*8+byte
        at=pa1+offset if offset<4096 else pa2+offset-4096
        write_ref(at,(value>>(8*byte))&255,1)
verify(pa1+0xff3,13);verify(pa2,21);traffic()
for flags,extra,cause in [(0x43,0,15),(0x47,0,15),(0,0,15),(0xc7,2<<61,7)]:
    second(flags,extra)
    op('vmv.v.i v8,9')
    op('vse64.v v8,(a0)',a=address,cause=cause,tval=va+4096)
    accesses+=8;write_ref(pa1+0xff4,9,8);state(4,1)
    verify(pa1+0xff3,13);verify(pa2,21);traffic()
    # Repair permissions and replay only elements 1..3 at the same VA.
    second();op('vse64.v v8,(a0)',a=address);accesses+=24
    for i in range(1,4):
        for byte in range(8):
            offset=0xff4+i*8+byte
            at=pa1+offset if offset<4096 else pa2+offset-4096
            write_ref(at,(9>>(8*byte))&255,1)
    state(4);verify(pa1+0xff3,13);verify(pa2,21);traffic()
for flags,extra,cause in [(0,0,13),(0xc7,2<<61,5)]:
    second(flags,extra);op('vmv.v.i v8,7')
    op('vle64.v v8,(a0)',a=address,cause=cause,tval=va+4096);accesses+=8;state(4,1)
    csr(8,0);elements(8,[9,7,7,7],64)
    csr(8,1);second();op('vle64.v v8,(a0)',a=address);accesses+=24
    elements(8,[9]*4,64);state(4);traffic()
second(0)
op('vle64ff.v v8,(a0)',a=address);accesses+=8;state(1);traffic()
config(4,64,'m2')
op('vle64ff.v v8,(a0)',a=va+4092,cause=13,tval=va+4096);state(4);traffic()
second();csr(8,0)
# Register overlap restrictions are checked before any physical access.
config(4,32)
op('vluxseg2ei32.v v8,(a0),v8',a=address,cause=2)
op('vslideup.vi v8,v8,1',cause=2)
op('vrgather.vv v8,v1,v8',cause=2)
op('vcompress.vm v8,v1,v8',cause=2)
op('viota.m v8,v8',cause=2)
op('vmsbf.m v8,v8',cause=2)
traffic()

# A segment restarts at field zero. No MMIO or PBMT=IO field may issue
# when a later field could fault and cause that access to be repeated.
second(0xc7,2<<61)
config(2,32)
op('vlseg2e32.v v8,(a0)',a=va+4092,cause=5,tval=va+4096)
accesses+=4;state(2);traffic()
op('vlseg2e32ff.v v8,(a0)',a=va+4088)
accesses+=8;state(1);traffic()
op('vle32.v v8,(a0)',a=va+4096)
accesses+=4;elements(8,[raw(pa2,4)],32);traffic()

packet(6,'.word 3')
config(2,32)
op('vlseg2e32.v v8,(a0)',a=0x10000018,cause=5,tval=0x10000018)
op('vsseg2e32.v v8,(a0)',a=0x10000018,cause=7,tval=0x10000018)
state(2);traffic()

# Coalescing witnesses: full words, group/row boundaries, fractional LMUL,
# nonzero vstart and a partial tail. Independent byte data remains the oracle.
packet(6,'.word 3')
coalescing_cases=0
for width in [8,16,32]:
    size=width//8;group=8//size
    for exponent in range(-3,4):
        if exponent<(width.bit_length()-1)-6:continue
        lmul=f'm{1<<exponent}' if exponent>=0 else f'mf{1<<-exponent}'
        count=(128<<exponent if exponent>=0 else 128>>-exponent)//width
        if count<2:continue
        config(count,width,lmul);op('vmv.v.i v8,7')
        length=count-1
        config(length,width,lmul);csr(8,1)
        packet(10,b=1)
        values=load(f'vle{width}.v v8,(a0)',base+0x12000,length,size,start=1)[0]
        i=1;groups=0
        while i<length:
            if i%group==0 and i+group<=length:groups+=1;i+=group
            else:i+=1
        packet(10,a=groups);state(length);traffic()
        config(count,width,lmul);elements(8,[7]+values[1:]+[7],width)
        coalescing_cases+=1

# The load EEW can differ from SEW; destination EMUL and packed RF offsets
# still follow the encoded memory width, not the arithmetic SEW.
for sew,width,count,destination_lmul in [(8,16,16,'m2'),(8,32,16,'m4'),(16,8,8,'mf2'),(16,32,8,'m2')]:
    config(count,sew);packet(10,b=1)
    values=load(f'vle{width}.v v8,(a0)',base+0x12000,count,width//8)[0]
    packet(10,a=count//(64//width));state(count);traffic()
    config(count,width,destination_lmul);elements(8,values,width)
    coalescing_cases+=1

# Adjacent NA4 PMP entries authorize both elements, but cannot authorize one
# wider word. The opportunity must fall back, not fault or read extra bytes.
packet(6,'.word 1')
packet(9,'.word 0',a=0x11,b=(base+0x12000)>>2)
packet(9,'.word 1',a=0x11,b=(base+0x12004)>>2)
config(2,32);packet(10,b=1)
values=load('vle32.v v8,(a0)',base+0x12000,2,4)[0]
packet(10,a=0);elements(8,values,32);traffic()
# Remove permission on the second element: first commits, precise vstart=1.
packet(9,'.word 1',a=0,b=0)
config(2,32);op('vmv.v.i v8,7');packet(10,b=1)
op('vle32.v v8,(a0)',a=base+0x12000,cause=5,tval=base+0x12004)
accesses+=4;packet(10,a=0);state(2,1);traffic()
config(2,32);elements(8,[raw(base+0x12000,4),7],32)

source=folder/'program.S';source.write_text('.text\n.option norvc\n'+'\n'.join(row[1] for row in program)+'\n')
files=(ROOT/'rtl/filelist.f').read_text().splitlines()+['tb/unit/backend/rv_vector_memory_engine_tb.sv']
with Simulator() as sim:
    obj=folder/'program.o';binary=folder/'program.bin'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcv_zvbb','-mabi=lp64d','-c',source,'-o',obj],folder/'assemble.log',60)
    sim.run([GCC/'riscv-none-elf-objcopy.exe','-O','binary','-j','.text',obj,binary],folder/'objcopy.log',60)
    data=binary.read_bytes();assert len(data)==4*len(program)
    vectors=folder/'program.hex';rows=[]
    for i,(kind,asm,a,b,value,exc,cause,tval) in enumerate(program):
        insn=struct.unpack_from('<I',data,i*4)[0]
        tval=(insn if cause==2 else 0) if tval is None else tval
        rows.append(f'{kind:x} {insn:08x} {a:016x} {b:016x} {value:016x} {exc:x} {cause:x} {tval:016x}')
    vectors.write_text('\n'.join(rows)+'\n')
    model=sim.build('rva23_vector_memory_engine','rv_vector_memory_engine_tb',files)
    model['run']=sim.simulate(model,[f'+vectors={vectors.relative_to(ROOT).as_posix()}']);model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'Vector memory owner Bare+Sv39: unit/stride/index/segments/masks/whole/FF/restart and second-page permissions/PBMT; native core integration has separate evidence',
        'packets':len(program),'physical_byte_accesses':accesses,'coalescing_cases':coalescing_cases,'model':model,'source_sha256':sha(source),
        'vectors_sha256':sha(vectors),'generator_sha256':sha(__file__)})
    print('PASS vector memory packets',len(program),'physical byte accesses',accesses,flush=True)

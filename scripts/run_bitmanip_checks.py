"""Independent Python results + GNU assembled B/Zicond encodings, RV32/RV64.

Also builds a self-checking RV64 ELF for execution through both OoO ALUs.
No new CoreMark ELF is created by this test.
"""
import json,random,struct
from sim_runner import ROOT,Simulator,GCC,sha,dump

out=ROOT/'out/rva23/bitmanip';out.mkdir(parents=True,exist_ok=True)
report={'passed':False,'cases':[],'scope':'B/Zicond block checks; RV64 integration ELF is separately run'}

def specs(xlen):
    result=[]
    for n in ['sh1add','sh2add','sh3add','andn','orn','xnor','min','minu','max','maxu',
              'rol','ror','bclr','bext','binv','bset','czero.eqz','czero.nez']:
        result.append((n,f'{n} t2,t0,t1',None))
    for n in ['clz','ctz','cpop','sext.b','sext.h','zext.h','orc.b','rev8']:
        result.append((n,f'{n} t2,t0',None))
    if xlen==64:
        for n in ['add.uw','sh1add.uw','sh2add.uw','sh3add.uw','rolw','rorw']:
            result.append((n,f'{n} t2,t0,t1',None))
        for n in ['clzw','ctzw','cpopw']:result.append((n,f'{n} t2,t0',None))
    for n in ['rori','bclri','bexti','binvi','bseti']+(['slli.uw','roriw'] if xlen==64 else []):
        for k in sorted({0,1,7,15,31,xlen-1,xlen//2}):
            if n=='roriw' and k>=32:continue
            result.append((n,f'{n} t2,t0,{k}',k))
    return result

def expected(n,a,b,k,xlen):
    mask=(1<<xlen)-1
    def signed(v,bits=xlen):return v-(1<<bits) if v>>(bits-1) else v
    word=n in ['rolw','rorw','roriw','clzw','ctzw','cpopw']
    width=32 if word else xlen;w_mask=(1<<width)-1
    if word:a&=w_mask
    shift=(b if k is None else k)&(width-1)
    op=n.rstrip('w') if word else n
    if op in ['sh1add','sh2add','sh3add']:v=(a<<int(op[2]))+b
    elif op in ['sh1add.uw','sh2add.uw','sh3add.uw']:v=((a&0xffffffff)<<int(op[2]))+b
    elif op=='add.uw':v=(a&0xffffffff)+b
    elif op=='slli.uw':v=(a&0xffffffff)<<shift
    elif op=='andn':v=a&~b
    elif op=='orn':v=a|~b
    elif op=='xnor':v=~(a^b)
    elif op=='min':v=a if signed(a)<signed(b) else b
    elif op=='minu':v=min(a,b)
    elif op=='max':v=a if signed(a)>signed(b) else b
    elif op=='maxu':v=max(a,b)
    elif op=='clz':v=width-a.bit_length()
    elif op=='ctz':v=(a&-a).bit_length()-1 if a else width
    elif op=='cpop':v=a.bit_count()
    elif op=='sext.b':v=signed(a&255,8)
    elif op=='sext.h':v=signed(a&65535,16)
    elif op=='zext.h':v=a&65535
    elif op=='rol':v=((a<<shift)|(a>>(width-shift)))&w_mask
    elif op in ['ror','rori']:v=((a>>shift)|(a<<(width-shift)))&w_mask
    elif op=='orc.b':v=sum((255 if (a>>(8*i))&255 else 0)<<(8*i) for i in range(xlen//8))
    elif op=='rev8':v=int.from_bytes(a.to_bytes(xlen//8,'little'),'big')
    elif op in ['bclr','bclri']:v=a&~(1<<shift)
    elif op in ['bext','bexti']:v=(a>>shift)&1
    elif op in ['binv','binvi']:v=a^(1<<shift)
    elif op in ['bset','bseti']:v=a|(1<<shift)
    elif op=='czero.eqz':v=a if b else 0
    elif op=='czero.nez':v=0 if b else a
    else:raise ValueError(n)
    if word:v=signed(v&w_mask,32)
    return v&mask

with Simulator() as sim:
    integration=[]
    for xlen in [32,64]:
        folder=out/str(xlen);folder.mkdir(exist_ok=True)
        operations=specs(xlen)
        assembly=folder/'encodings.S'
        assembly.write_text('.text\n.option norvc\n'+ '\n'.join(x[1] for x in operations)+'\n')
        obj=folder/'encodings.o';binary=folder/'encodings.bin'
        march=f'rv{xlen}imfc_zicsr_zifencei_zba_zbb_zbs_zicond'
        run,_=sim.run([GCC/'riscv-none-elf-gcc.exe','-c','-march='+march,
            '-mabi='+('ilp32f' if xlen==32 else 'lp64f'),assembly,'-o',obj],folder/'assemble.log',60)
        sim.run([GCC/'riscv-none-elf-objcopy.exe','-j','.text','-O','binary',obj,binary],folder/'objcopy.log',30)
        data=binary.read_bytes();assert len(data)==4*len(operations)
        rng=random.Random(0x52564123+xlen);mask=(1<<xlen)-1
        values=[0,1,2,7,31,32,63,mask,mask>>1,1<<(xlen-1),0xffffffff&mask,0x80000000,
                0x80ff01007f00aa55&mask,0xffffffff80000001&mask]
        vectors=[]
        for idx,(n,_,k) in enumerate(operations):
            insn=struct.unpack_from('<I',data,idx*4)[0]
            pairs=[(a,b) for a in values for b in [0,1,xlen-1,mask,1<<(xlen-1)]]
            pairs += [(rng.getrandbits(xlen),rng.getrandbits(xlen)) for _ in range(32)]
            for a,b in pairs:
                answer=expected(n,a,b,k,xlen)
                vectors.append((insn,a,b,answer,0))
            if xlen==64:
                for a,b in [pairs[0],pairs[10],pairs[-1]]:
                    integration.append((insn,a,b,expected(n,a,b,k,xlen)))
        bad=[0x60329393,0x60729393,0x0802c3b3 | (1<<20)]
        bad += [0x0802c3bb | (1<<20)] if xlen==64 else [0x2002a3bb,0x6b82d393,0x2a029393]
        bad += [0x6982d393] if xlen==64 else []
        vectors += [(i,0,0,0,1) for i in bad]
        vector_path=folder/'vectors.hex'
        vector_path.write_text('\n'.join(f'{i:08x}{a:016x}{b:016x}{v:016x}{f:08x}' for i,a,b,v,f in vectors)+'\n')
        files=['rtl/rv_ooo_pkg.sv','rtl/backend/rv_fp_decode_pkg.sv','rtl/backend/rv_vector_decode_pkg.sv','rtl/frontend/rv_c_expander.sv','rtl/backend/rv_hypervisor_decode_pkg.sv','rtl/backend/rv_decode2.sv',
               'rtl/backend/rv_int_alu.sv','tb/unit/backend/rv_bitmanip_tb.sv']
        model=sim.build(f'rva23_bitmanip_{xlen}','rv_bitmanip_tb',files,[f'-GXLEN={xlen}'])
        model['run']=sim.simulate(model,[f'+vectors={vector_path.relative_to(ROOT).as_posix()}',f'+count={len(vectors)}'])
        model.update(passed=True,vectors=vector_path.relative_to(ROOT).as_posix(),vector_sha256=sha(vector_path),
                     generator_sha256=sha(__file__),checks=len(vectors),assembled_operations=len(operations))
        report['cases'].append(model);dump(out/'report.json',report)
        print('PASS B/Zicond XLEN',xlen,'vectors',len(vectors),'encodings',len(operations),flush=True)
    asm=out/'rv64_integration.S'
    lines=['.section .text.init,"ax"','.option norvc','.globl _start','_start:',
           'lui t0,0x02000','sw zero,0(t0)',
           'csrr t0,misa','andi t0,t0,2','beqz t0,fail']
    for insn,a,b,v in integration:
        lines += [f'li t0,0x{a:016x}',f'li t1,0x{b:016x}',f'.word 0x{insn:08x}',
                  f'li t3,0x{v:016x}','bne t2,t3,fail']
    lines += ['lui t0,0x10000','li t1,0x42323331','sw t1,0xc(t0)','sw zero,0x14(t0)',
              '1: wfi','j 1b','fail:','lui t0,0x10000','li t1,1','sw t1,0x14(t0)','j 1b']
    asm.write_text('\n'.join(lines)+'\n')
    elf=out/'rv64_integration.elf'
    program,_=sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imfc_zicsr_zifencei_zba_zbb_zbs_zicond',
        '-mabi=lp64f','-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld',asm,'-o',elf],out/'integration_compile.log',60)
    report.update(passed=True,integration_elf=elf.relative_to(ROOT).as_posix(),integration_elf_sha256=sha(elf),
                  integration_assembly_sha256=sha(asm),integration_cases=len(integration))
    dump(out/'report.json',report)
    print('PASS prepared RV64 B/Zicond integration ELF cases',len(integration),flush=True)

"""GNU independently assembles each compressed form and canonical equivalent."""
import struct
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/compressed';folder.mkdir(parents=True,exist_ok=True)
report={'passed':False,'cases':[]}
with Simulator() as sim:
    for xlen in [32,64]:
        pairs=[]
        for a in range(8,16):
            for b in range(8,16):
                for k in range(4):
                    pairs += [(f'c.lbu x{a},{k}(x{b})',f'lbu x{a},{k}(x{b})'),
                              (f'c.sb x{a},{k}(x{b})',f'sb x{a},{k}(x{b})')]
                for k in [0,2]:
                    pairs += [(f'c.lhu x{a},{k}(x{b})',f'lhu x{a},{k}(x{b})'),
                              (f'c.lh x{a},{k}(x{b})',f'lh x{a},{k}(x{b})'),
                              (f'c.sh x{a},{k}(x{b})',f'sh x{a},{k}(x{b})')]
                pairs.append((f'c.mul x{a},x{b}',f'mul x{a},x{a},x{b}'))
            for op,canonical in [('zext.b',f'andi x{a},x{a},255'),
                ('sext.b',f'sext.b x{a},x{a}'),('zext.h',f'zext.h x{a},x{a}'),
                ('sext.h',f'sext.h x{a},x{a}'),('not',f'xori x{a},x{a},-1')]+(
                [('zext.w',f'add.uw x{a},x{a},zero')] if xlen==64 else []):
                pairs.append((f'c.{op} x{a}',canonical))
        pairs += [(f'c.mop.{n}','addi zero,zero,0') for n in range(1,16,2)]
        source=folder/f'rv{xlen}.S';obj=folder/f'rv{xlen}.o';raw=folder/f'rv{xlen}.bin'
        source.write_text('.text\n'+''.join(f'.option push\n.option arch,+zca,+zcb,+zcmop\n{a}\n.option pop\n.option norvc\n{b}\n' for a,b in pairs),encoding='utf-8')
        sim.run([GCC/'riscv-none-elf-gcc.exe',f'-march=rv{xlen}imc_zba_zbb_zcb_zcmop',
            '-mabi='+('ilp32' if xlen==32 else 'lp64'),'-c',source,'-o',obj],folder/f'rv{xlen}_compile.log',60)
        sim.run([GCC/'riscv-none-elf-objcopy.exe','-O','binary','-j','.text',obj,raw],folder/f'rv{xlen}_objcopy.log',60)
        data=raw.read_bytes();assert len(data)==6*len(pairs),(len(data),len(pairs))
        vectors=folder/f'rv{xlen}.hex'
        vectors.write_text(''.join(f'{struct.unpack_from("<I",data,i+2)[0]:08x}{struct.unpack_from("<H",data,i)[0]:04x}\n'
            for i in range(0,len(data),6)),encoding='utf-8')
        model=sim.build(f'rva23_compressed_{xlen}','rv_compressed_profile_tb',[
            'rtl/frontend/rv_c_expander.sv','tb/unit/backend/rv_compressed_profile_tb.sv'],[
            f'-GXLEN={xlen}',f'-GCASES={len(pairs)}',f'-GVECTOR_FILE="{vectors.relative_to(ROOT).as_posix()}"'])
        model['run']=sim.simulate(model);model['passed']=True
        report['cases'].append({'xlen':xlen,'vectors':len(pairs),'vector_sha256':sha(vectors),
            'assembly_sha256':sha(source),'model':model})
        print('PASS compressed profile RV',xlen,'GNU vectors',len(pairs),'all 65536 encodings checked',flush=True)
    report['passed']=True;dump(folder/'report.json',report)

"""Execute development vector streams as real ELF instructions in the OoO SoC.

ELFs here are functional tests, never replacements for fixed IPC benchmarks.
The memory stream is relocated into SRAM above the program and stops before
its standalone Sv39 context switch; supervisor integration has a separate test.
"""
import csv,json,struct
from sim_runner import ROOT,Simulator,GCC,sha,dump,source_inputs
folder=ROOT/'out/rva23/vector_integration';folder.mkdir(parents=True,exist_ok=True)
files=(ROOT/'rtl/filelist.f').read_text().splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
params=['-GXLEN=64','-GHAS_V=1','-GHAS_H=1','-GHAS_MISALIGNED=1','-GHAS_D=1','-GHAS_ZFHMIN=1','-GHAS_ZFA=1',
    '-GHAS_ZAWRS=1','-GHAS_ZIMOP=1','-GHAS_ZCMOP=1','-GHAS_ZCB=1','-GHAS_SVINVAL=1','-GHAS_SSNPM=1',
    '-GHAS_CBO=1','-GHAS_A=1','-GHAS_B=1','-GHAS_ZICOND=1','-GHAS_SMODE=1','-GHAS_MMU=1']
mask=(1<<64)-1
runtime_inputs={'tb/fixtures/bootrom/bootrom_host_jump64.hex':sha(ROOT/'tb/fixtures/bootrom/bootrom_host_jump64.hex')}
def relocate(value):
    return value+0x80000 if 0x80000000<=value<0x80080000 else value
def generate(name):
    packet_path=ROOT/f'out/rva23/{name}/program.hex'
    packets=[[int(x,16) for x in line.split()] for line in packet_path.read_text().splitlines()]
    code=['.section .text.init,"ax"','.option norvc','.globl _start','_start:',
          'lui t0,0x02000','sw zero,0(t0)','la t0,m_trap','csrw mtvec,t0',
          'li t0,0x2200','csrw mstatus,t0','li s6,0','li s7,0']
    traps=[];count=0
    def compare(register,value):
        code.extend([f'li t5,0x{value&mask:016x}',f'bne {register},t5,fail'])
    for row in packets:
        if name=='vector_memory_engine':
            kind,insn,a,b,value,exc,cause,tval=row
            if kind==6:break
            a=relocate(a);tval=relocate(tval)
            flags=0;frm=0;fp_enabled=1;sat=2
        else:
            kind,insn,a,b,value,exc,sat,flags,frm,fp_enabled=row
            cause=(5 if insn&0x7f in [7,0x27] else 2) if exc else 0
            tval=insn if cause==2 else a
        code.append(f'li s7,{count}')
        if kind==1:
            code.extend([f'li t0,0x{a:016x}',f'csrw 0x{insn&4095:03x},t0'])
        elif kind in [2,7]:
            code.extend([f'li t0,0x{a:016x}',f'li t1,0x{b:016x}',('sb' if kind==2 else 'sd')+' t1,0(t0)'])
        elif kind==3:
            code.extend([f'li t0,0x{a:016x}','lbu t1,0(t0)']);compare('t1',value&255)
        elif kind==4:
            code.append('csrr t1,vl');compare('t1',a)
            code.append('csrr t1,vstart');compare('t1',b)
        elif kind==5:pass # physical traffic is checked by the standalone TB
        elif kind==8:code.append('sfence.vma')
        else:
            code.extend(['li t0,0x2000','csrs mstatus,t0','csrw fflags,zero',f'li t0,{frm}','csrw frm,t0',
                         f'li t0,{0x2000 if fp_enabled else 0}','li t1,0x6000','csrc mstatus,t1','csrs mstatus,t0',
                         f'li a0,0x{a:016x}',f'li a1,0x{b:016x}'])
            # Scalar FP operands occupy fa0 in all GNU VF stream forms.
            # Move while FS enabled, then restore the intended FS permission.
            if insn&0x7f==0x57 and (insn>>12)&7==5:
                code.extend(['li t0,0x2000','csrs mstatus,t0','fmv.d.x fa0,a0'])
                if not fp_enabled:code.extend(['li t0,0x6000','csrc mstatus,t0'])
            code.extend([f'li s8,{cause}',f'li s9,0x{tval&mask:016x}',f'li s10,{int(bool(exc))}',f'.word 0x{insn:08x}'])
            code.append('bnez s10,fail')
            if exc:traps.append(cause)
            else:
                # Scalar destinations: vset*, vmv.x.s/vcpop.m/vfirst.m,
                # and vfmv.f.s. Other operations only update vector state.
                f3=(insn>>12)&7;family=insn>>26;rs1=(insn>>15)&31;rd=(insn>>7)&31
                scalar_fp=insn&0x7f==0x57 and f3==1 and family==0x10 and rs1==0
                scalar_int=insn&0x7f==0x57 and (f3==7 or (f3==2 and family==0x10 and rs1 in [0,16,17]))
                if scalar_fp:code.append(f'fmv.x.d t1,f{rd}');compare('t1',value)
                elif scalar_int and rd:compare(f'x{rd}',value)
                if fp_enabled:code.append('csrr t1,fflags');compare('t1',flags)
            if sat!=2:code.append('csrr t1,vxsat');compare('t1',sat)
        count+=1
    code+=['li t0,'+str(len(traps)),'bne s6,t0,fail','lui t0,0x10000','li t1,0x56454331','sw t1,0xc(t0)',
           'sw zero,0x14(t0)','1:j 1b','m_trap:','beqz s10,fail','csrr t4,mcause','bne t4,s8,fail',
           'csrr t4,mtval','bne t4,s9,fail','li s10,0','addi s6,s6,1',
           'csrr t4,mepc','addi t4,t4,4','csrw mepc,t4','mret',
           'fail:','lui t0,0x10000','sw s7,0xc(t0)','li t1,1','sw t1,0x14(t0)','j 1b']
    if name=='vector_memory_engine':
        code+=['.section .fixture,"aw"']
        for offset in range(0,65536,16):code.append('.byte '+','.join(str((i*37+11)&255) for i in range(offset,offset+16)))
        code+=['.section .edge,"aw"','.byte '+','.join(str((i*37+11)&255) for i in range(0xffff0,0x100000))]
    source=folder/(name+'.S');source.write_text('\n'.join(code)+'\n')
    return source,count,traps,packet_path
link=folder/'vector.ld'
link.write_text('''OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {
 . = 0x80020000; .text : { *(.text.init) *(.text .text.*) *(.rodata .rodata.*) }
 ASSERT(. < 0x80080000, "Vector program overlaps fixtures")
 . = 0x80080000; .fixture : { *(.fixture) }
 . = 0x800ffff0; .edge : { *(.edge) }
 /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.riscv.attributes) }
}
''')
generated=[(name,*generate(name)) for name in ['vector_integer_engine','vector_fp_engine','vector_memory_engine']]
with Simulator() as sim:
    path=folder/'model.json';old=json.loads(path.read_text()) if path.exists() else None
    inputs=source_inputs(files)
    # Reuse the identical full-profile development model when available.
    # Input, parameter and executable hashes must all agree before reuse.
    h_path=ROOT/'out/rva23/hypervisor_integration/model.json'
    if h_path.exists():
        candidate=json.loads(h_path.read_text())
        if candidate['inputs']==inputs and candidate['params']==params and sha(ROOT/candidate['binary'])==candidate['binary_sha256']:
            old=candidate
    if old and old['inputs']==inputs and old['params']==params and sha(ROOT/old['binary'])==old['binary_sha256']:model=old
    else:model=sim.build('rva23_vector_core','rv32_program_tb',files,params)
    dump(path,model)
    cases=[]
    for name,source,count,traps,packet_path in generated:
        elf=folder/(name+'.elf');trace=folder/(name+'_commit.csv')
        sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcv_zvbb_zvfhmin','-mabi=lp64d','-nostdlib','-nostartfiles',
            '-Wl,--no-relax','-Wl,--build-id=none','-T',link,source,'-o',elf],folder/(name+'_compile.log'),60)
        run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit','+timeout_cycles=10000000','+expected_exit_code=0'],
            folder/(name+'_simulation.log'),300)
        assert 'PASS rv32_program_tb' in text and 'data=0x56454331' in text
        with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
        actual=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
        assert [int(r['cause']) for r in actual]==traps,actual
        cases.append({'name':name,'packets':count,'passed':True,'traps':actual,'run':run,
            'source_sha256':sha(source),'packet_sha256':sha(packet_path),'elf_sha256':sha(elf),'trace_sha256':sha(trace)})
        dump(folder/'progress.json',cases)
        print('PASS full-core vector',name,count,'packets',flush=True)
    for p,h in inputs.items():assert sha(ROOT/p)==h,p
    for p,h in runtime_inputs.items():assert sha(ROOT/p)==h,p
    dump(folder/'report.json',{'passed':True,'scope':'Architectural V integration, integer/FP/Bare memory streams on the H-enabled SoC; full profile sign-off pending',
        'model':model,'cases':cases,'runtime_inputs':runtime_inputs,'generator_sha256':sha(__file__),'linker_sha256':sha(link)})

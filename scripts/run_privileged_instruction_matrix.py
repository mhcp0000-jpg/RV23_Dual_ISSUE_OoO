"""Native instruction permission matrix on the integrated H-enabled RV64 SoC.

Expected results are computed from Privileged ISA 1.13 Svinval/H/return/WFI/Sstc
rules, independently of RTL decoders. This is a functional ELF, not a benchmark.
"""
import argparse,csv,itertools,json
from sim_runner import ROOT,Simulator,GCC,sha,dump,source_inputs

parser=argparse.ArgumentParser()
parser.add_argument('--group',choices=['all','fence','wfi','return','csr','env','pmp','sstc'],default='all')
args=parser.parse_args()
folder=ROOT/'out/rva23'/('privileged_instruction_matrix'+('' if args.group=='all' else '_'+args.group))
folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
assert '-GHAS_H=1' in model['params'] and '-GXLEN=64' in model['params']
runtime={p:sha(ROOT/p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex','sw/benchmarks/coremark/rv32_tim.ld']}
def fresh():
    files=(ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()+[
        'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
    assert model['inputs']==source_inputs(files)
    for p,h in {**model['inputs'],**runtime}.items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()

cases=[]
def add(mode,instruction,opcode,cause,**fields):
    cases.append(dict(id=len(cases)+1,mode=mode,instruction=instruction,opcode=opcode,cause=cause,**fields))

if args.group in ['all','fence']:
    forms=[('sfence.w.inval',0x18000073,'order'),('sfence.inval.ir',0x18100073,'order'),
           ('sfence.vma',0x12000073,'s'),('sinval.vma',0x16000073,'s'),
           ('hfence.vvma',0x22000073,'h'),('hinval.vvma',0x26000073,'h'),
           ('hfence.gvma',0x62000073,'g'),('hinval.gvma',0x66000073,'g'),
           ('fence.i',0x0000100f,'user')]
    for mode,tvm,vtvm in itertools.product(['VU','U','VS','HS','M'],range(2),range(2)):
        for instruction,opcode,kind in forms:
            cause=0
            if kind!='user':
                if mode=='VU':cause=22
                elif mode=='U':cause=2
                elif mode=='VS' and (kind in ['h','g'] or kind=='s' and vtvm):cause=22
                elif mode=='HS' and kind in ['s','g'] and tvm:cause=2
            add(mode,instruction,opcode,cause,tvm=tvm,vtvm=vtvm)
if args.group in ['all','wfi']:
    for mode,tw,vtw in itertools.product(['U','VU','VS','HS','M'],range(2),range(2)):
        # This implementation traps U-mode WFI when S-mode exists. Legal
        # privileged cases have a locally enabled pending interrupt with their
        # current-level global enable clear, so WFI wakes without taking it.
        cause=2 if mode=='U' or mode!='M' and tw else (
            22 if mode=='VU' or mode=='VS' and vtw else 0)
        add(mode,'wfi',0x10500073,cause,tw=tw,vtw=vtw)
if args.group in ['all','return']:
    for mode,tsr,vtsr in itertools.product(['VU','U','VS','HS','M'],range(2),range(2)):
        cause=22 if mode=='VU' or mode=='VS' and vtsr else (
            2 if mode=='U' or mode=='HS' and tsr else 0)
        add(mode,'sret',0x10200073,cause,tsr=tsr,vtsr=vtsr)
    for mode in ['VU','U','VS','HS','M']:
        add(mode,'mret',0x30200073,0 if mode=='M' else 2)
if args.group in ['all','csr']:
    for mode in ['M','HS','VS','U','VU']:
        add(mode,'mconfigptr_read',0xf15022f3,0 if mode=='M' else 2,read_value=0)
        # Even a zero-value CSRRW with rd=x0 must attempt a write and trap.
        add(mode,'mconfigptr_write',0xf1501073,2)
if args.group in ['all','pmp']:
    # PMP exposes a 16-entry CSR group; eight usable entries plus eight RAZ
    # entries are legal. Lower modes must still trap on every PMP CSR access.
    for mode in ['M','HS','VS','U','VU']:
        for address in [*range(0x3b8,0x3c0),0x3a2]:
            for label,bits in [('read',0x22f3),('write_zero',0x12f3),('write_ones',0xfd2f3)]:
                add(mode,f'pmp_{address:03x}_{label}',(address<<20)|bits,
                    0 if mode=='M' else 2,read_value=0)
        add(mode,'pmpcfg1_reserved_rv64',0x3a1022f3,2)
if args.group in ['all','env']:
    for mode in ['M','HS','VS','U','VU']:
        add(mode,'menvcfg_read',0x30a022f3,0 if mode=='M' else 2,read_value=1)
        add(mode,'henvcfg_read',0x60a022f3,22 if mode in ['VS','VU'] else (2 if mode=='U' else 0),read_value=1)
        add(mode,'senvcfg_read',0x10a022f3,22 if mode=='VU' else (2 if mode=='U' else 0),read_value=1)

if args.group=='sstc':
    gates=itertools.product(range(2),repeat=4)
    for mode,(mtm,mstce,htm,hstce) in itertools.product(['M','HS','VS','U','VU'],gates):
        for address in [0x14d,0x24d]:
            cause=0
            if mode=='U' or (mode!='M' and not (mtm and mstce)):
                cause=2
            elif mode=='VU' or (mode=='VS' and (address==0x24d or not (htm and hstce))):
                cause=22
            add(mode,f'timer_{address:03x}_read',(address<<20)|0x22f3,cause,
                mtm=mtm,mstce=mstce,htm=htm,hstce=hstce,
                read_value=1000 if mode=='VS' or address==0x24d else 1200)

lines=['.section .text.init,"ax"','.option norvc','.globl _start','_start:',
       '  lui t0,0x02000','  sw zero,0(t0)','  la t0,m_trap','  csrw mtvec,t0',
       '  li t0,-1','  csrw pmpaddr0,t0','  li t0,31','  csrw pmpcfg0,t0',
       '  csrw medeleg,zero','  li s10,0','  j setup_1']
for c in cases:
    n=c['id'];mode=c['mode'];priv=3 if mode=='M' else 1 if mode in ['HS','VS'] else 0
    virtual=mode in ['VS','VU']
    status=(priv<<11)|(int(virtual)<<39)|(c.get('tvm',0)<<20)|(c.get('tw',0)<<21)|(c.get('tsr',0)<<22)|0x100
    hstatus=(c.get('vtvm',0)<<20)|(c.get('vtw',0)<<21)|(c.get('vtsr',0)<<22)
    exitmode='HS' if c['instruction']=='sret' and c['cause']==0 and mode=='M' else mode
    ecall=11 if exitmode=='M' else 10 if exitmode=='VS' else 9 if exitmode=='HS' else 8
    c['ecall_cause']=ecall
    lines.extend([f'setup_{n}:',f'  li s0,{n}',f'  li s1,{c["cause"]}',f'  li s2,{c["opcode"]}',
                  f'  la s3,probe_{n}',f'  la s4,after_{n}',f'  la s11,ecall_{n}',
                  f'  la s5,{"finish" if n==len(cases) else "setup_"+str(n+1)}',
                  '  li s6,0',f'  li s8,{ecall}',f'  li s9,{(priv<<11)|(int(virtual)<<39)}',
                  '  csrw mie,zero','  csrw mip,zero','  csrw hvip,zero',
                  '  li t0,1','  csrw menvcfg,t0','  csrw senvcfg,t0','  csrw henvcfg,t0',
                  '  li t0,0xc000000000000000','  csrw hstateen0,t0',
                  f'  li t0,{hstatus}','  csrw hstatus,t0','  li t0,0x100','  csrw vsstatus,t0',
                  f'  la t0,after_{n}','  csrw sepc,t0','  csrw vsepc,t0',
                  f'  li t0,{status}','  csrw mstatus,t0'])
    if 'mtm' in c:
        lines.extend([f'  li t0,{c["mtm"]<<1}','  csrw mcounteren,t0',
                      f'  li t0,{c["mstce"]<<63}','  csrw menvcfg,t0',
                      f'  li t0,{c["htm"]<<1}','  csrw hcounteren,t0',
                      f'  li t0,{c["hstce"]<<63}','  csrw henvcfg,t0',
                      '  li t0,1000','  csrw vstimecmp,t0',
                      '  li t0,1200','  csrw stimecmp,t0'])
    if c['instruction']=='wfi' and c['cause']==0:
        if mode=='M':
            lines.extend(['  li t0,8','  csrw mie,t0','  lui t0,0x02000','  li t1,1','  sw t1,0(t0)'])
        elif mode=='HS':
            lines.extend(['  li t0,2','  csrw mideleg,t0','  csrw mie,t0','  csrw mip,t0'])
        elif mode=='VS':
            lines.extend(['  li t0,4','  csrw hideleg,t0','  csrw mie,t0','  csrw hvip,t0'])
    if mode=='M':
        if c['instruction']=='mret':lines.extend([f'  la t0,after_{n}','  csrw mepc,t0'])
        lines.append(f'  j probe_{n}')
    else:lines.extend([f'  la t0,probe_{n}','  csrw mepc,t0','  mret'])
    lines.extend([f'probe_{n}:',f'  .word {c["opcode"]}',f'after_{n}:'])
    if c['cause']==0 and 'read_value' in c:
        lines.extend([f'  li t1,{c["read_value"]}','  bne t0,t1,fail'])
        if c['instruction'].endswith('envcfg_read'):lines.append('  fence io,io')
    lines.extend([f'ecall_{n}:','  ecall','  j fail'])
lines.extend(['m_trap:',
    '  csrr t0,mcause','  beq t0,s8,case_done','  beqz s1,fail','  bne t0,s1,fail',
    '  bnez s6,fail','  csrr t0,mtval','  bne t0,s2,fail','  csrr t0,mepc','  bne t0,s3,fail',
    '  csrr t0,mstatus','  li t1,0x8000001800','  and t0,t0,t1','  bne t0,s9,fail',
    '  li s6,1','  csrw mepc,s4','  mret',
    'case_done:','  csrr t0,mepc','  bne t0,s11,fail','  snez t0,s1','  bne t0,s6,fail',
    '  addi s10,s10,1','  lui t0,0x02000','  sw zero,0(t0)',
    '  csrw mie,zero','  csrw mip,zero','  csrw hvip,zero','  csrw mstatus,zero','  jr s5',
    'finish:',f'  li t0,{len(cases)}','  bne s10,t0,fail',
    '  lui t0,0x10000','  li t1,0x50525631','  sw t1,0xc(t0)','  sw zero,0x14(t0)','1:j 1b',
    'fail:','  lui t0,0x10000','  sw s0,0xc(t0)','  li t1,1','  sw t1,0x14(t0)','  j 1b'])
source=folder/'test.S';source.write_text('\n'.join(lines)+'\n',encoding='utf-8')
dump(folder/'cases.json',cases)
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    compile_record,_=sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh_svinval','-mabi=lp64d',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=400000','+expected_exit_code=0'],folder/'simulation.log',180)
    fresh()
    assert 'PASS rv32_program_tb' in text and 'data=0x50525631' in text
    with trace.open(newline='') as stream:
        traps=[row for row in csv.DictReader(stream) if row['trap']=='1' and int(row['pc'],16)>=0x80000000]
    expected=[]
    for c in cases:
        if c['cause']:expected.append(c['cause'])
        expected.append(c['ecall_cause'])
    assert [int(row['cause']) for row in traps]==expected
    dump(folder/'report.json',dict(passed=True,scope=f'Native M/HS/VS/U/VU instruction permission group {args.group}',
        model=model,runtime_inputs=runtime,generator_sha256=sha(__file__),source_sha256=sha(source),
        cases_sha256=sha(folder/'cases.json'),elf_sha256=sha(elf),trace_sha256=sha(trace),
        compile=compile_record,run=run,case_count=len(cases),expected_traps=expected,traps=traps))
print(f'PASS native privileged instruction matrix: {len(cases)} cases / {len(traps)} precise traps',flush=True)

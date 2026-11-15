"""Native S/VS faults on the second parcel of a page-straddling instruction."""
import csv
import json

from sim_runner import ROOT, Simulator, GCC, dump, sha, source_inputs


def main():
    folder = ROOT / 'out/rva23/split_fetch_faults'
    folder.mkdir(parents=True, exist_ok=True)
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    assert all(p in model['params'] for p in ['-GHAS_H=1','-GHAS_V=1','-GXLEN=64'])
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
    inputs = source_inputs(files)
    assert model['inputs'] == inputs
    runtime = {p:sha(ROOT / p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex',
                                        'sw/benchmarks/coremark/rv32_tim.ld']}

    def fresh():
        for p,digest in {**inputs,**runtime}.items():
            assert sha(ROOT / p) == digest, p
        assert sha(ROOT / model['binary']) == model['binary_sha256']

    fresh()
    cases = [dict(id=i+1, mode=mode, target=target, kind=kind, cause=12 if kind=='page' else 1)
             for i,(mode,target,kind) in enumerate((m,t,k) for m,t in [
                 ('HS','M'),('HS','HS'),('VS','M'),('VS','HS'),('VS','VS')]
                 for k in ['page','access'])]
    for target in ['M','HS']:
        cases.append(dict(id=len(cases)+1,mode='VS',target=target,kind='gstage',cause=20))
    for case in cases:
        case.update(instruction_pc=0x40000ffe,fault_address=0x40001000,
                    guest_address=0x80041000 if case['kind']=='gstage' else 0)
    lines = ['.section .text.init,"ax"','.option norvc','.option norelax','.globl _start','_start:',
        'lui t0,0x02000','sw zero,0(t0)','li t0,-1','csrw pmpaddr0,t0','li t0,31','csrw pmpcfg0,t0',
        'la t0,root','li t1,0x200000cf','sd t1,16(t0)',
        'la t1,level1','srli t1,t1,2','ori t1,t1,1','sd t1,8(t0)',
        'la t0,level1','la t1,level0','srli t1,t1,2','ori t1,t1,1','sd t1,0(t0)',
        'la t0,level0','li t1,(0x80040000 >> 2) | 0xcb','sd t1,0(t0)',
        'li t0,0x80040ffe','li t1,0x0293','sh t1,0(t0)',
        'li t0,0x80041000','li t1,0x1230','sh t1,0(t0)','fence.i',
        'la t0,groot','la t1,glevel1','srli t1,t1,2','ori t1,t1,1','sd t1,16(t0)',
        'la t0,glevel1','la t1,glevel0','srli t1,t1,2','ori t1,t1,1','sd t1,0(t0)',
        'la t0,glevel0','li t1,0x200000df','li t2,256',
        'fill_gstage:','sd t1,0(t0)','addi t0,t0,8','addi t1,t1,1024',
        'addi t2,t2,-1','bnez t2,fill_gstage',
        'la t0,glevel0','sd zero,520(t0)', # deny only GPA page 0x80041000
        'li a0,0','j setup_1']
    for c in cases:
        n, guest, target = c['id'], c['mode']=='VS', c['target']
        lines += [f'setup_{n}:',f'li s0,{n}',f'li s1,{c["cause"]}',
            'li s2,0x40001000','li s3,0x40000ffe',f'la s4,resume_{n}',
            f'la s5,{"finish" if n==len(cases) else "setup_"+str(n+1)}',
            f'li s6,{["M","HS","VS"].index(target)}',f'li s7,{int(guest)}',
            f'li s8,{10 if guest else 9}',f'li s9,{0x80041000>>2 if c["kind"]=="gstage" else 0}','li a1,0',
            'la t0,m_trap','csrw mtvec,t0','la t0,hs_trap','csrw stvec,t0',
            'la t0,vs_trap','csrw vstvec,t0',
            f'li t0,{0 if target=="M" else 1<<c["cause"]}','csrw medeleg,t0',
            f'li t0,{1<<c["cause"] if target=="VS" else 0}','csrw hedeleg,t0',
            'li t0,0x40','csrw hstatus,t0','csrw hgatp,zero','csrw vsstatus,zero',
            'la t0,level0',f'li t1,{0 if c["kind"]=="page" else (0x80041000>>2)|0xcb}','sd t1,8(t0)',
            'csrw pmpcfg0,zero']
        if c['kind']=='access':
            lines += ['li t0,(0x80041000 >> 2) | 0x1ff','csrw pmpaddr0,t0',
                      'li t0,-1','csrw pmpaddr1,t0','li t0,0x1f18','csrw pmpcfg0,t0']
        else:
            lines += ['li t0,-1','csrw pmpaddr0,t0','li t0,31','csrw pmpcfg0,t0']
        lines += ['la t0,root','srli t0,t0,12','li t1,0x8000000000000000','or t0,t0,t1',
                  f'csrw {"vsatp" if guest else "satp"},t0']
        if guest:
            lines += ['csrw satp,zero']
        else:
            lines += ['csrw vsatp,zero']
        if c['kind']=='gstage':
            lines += ['la t0,groot','srli t0,t0,12','li t1,0x8000000000000000',
                      'or t0,t0,t1','csrw hgatp,t0']
        lines += ['sfence.vma','hfence.vvma','hfence.gvma',
                  f'li t0,{0x800 | (int(guest)<<39) | (1<<38)}','csrw mstatus,t0',
                  'csrw mepc,s3','mret',f'resume_{n}:','ecall','j fail']
    lines += ['.balign 4','m_trap:','csrr t0,mcause','beq t0,s8,case_done',
        'bnez s6,fail','bne t0,s1,fail','csrr t0,mtval','bne t0,s2,fail',
        'csrr t0,mepc','bne t0,s3,fail','csrr t0,mtval2','bne t0,s9,fail',
        'csrr t0,mtinst','bnez t0,fail','csrr t0,mstatus','srli t1,t0,38',
        'andi t1,t1,1','bne t1,s7,fail','srli t1,t0,39','andi t1,t1,1','bne t1,s7,fail',
        'addi a1,a1,1','csrw mepc,s4','mret',
        '.balign 4','hs_trap:','li t0,1','bne s6,t0,fail','csrr t0,scause','bne t0,s1,fail',
        'csrr t0,stval','bne t0,s2,fail','csrr t0,sepc','bne t0,s3,fail',
        'csrr t0,htval','bne t0,s9,fail','csrr t0,htinst','bnez t0,fail',
        'csrr t0,hstatus','srli t1,t0,6','andi t1,t1,1','bne t1,s7,fail',
        'srli t1,t0,7','andi t1,t1,1','bne t1,s7,fail',
        'addi a1,a1,1','csrw sepc,s4','sret',
        '.balign 4','vs_trap:','li t0,2','bne s6,t0,fail','csrr t0,scause','bne t0,s1,fail',
        'csrr t0,stval','bne t0,s2,fail','csrr t0,sepc','bne t0,s3,fail',
        'addi a1,a1,1','csrw sepc,s4','sret',
        'case_done:','csrr t0,mepc','bne t0,s4,fail','li t0,1','bne a1,t0,fail',
        'addi a0,a0,1','csrw mstatus,zero','csrw satp,zero','csrw vsatp,zero','jr s5',
        'finish:',f'li t0,{len(cases)}','bne a0,t0,fail','lui t0,0x10000',
        'li t1,0x53504c54','sw t1,0xc(t0)','sw zero,0x14(t0)','halt:j halt',
        'fail:','lui t0,0x10000','sw s0,0xc(t0)','li t1,1','sw t1,0x14(t0)','j halt',
        '.section .bss,"aw",@nobits','.balign 4096','root:.space 4096',
        'level1:.space 4096','level0:.space 4096','.balign 16384','groot:.space 16384',
        'glevel1:.space 4096','glevel0:.space 4096']
    source,elf,trace = folder/'test.S',folder/'test.elf',folder/'commit.csv'
    source.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    dump(folder/'cases.json',cases)
    with Simulator() as sim:
        compile_run,_ = sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh','-mabi=lp64d',
            '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
            '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
        run,text = sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
            '+timeout_cycles=500000','+expected_exit_code=0'],folder/'simulation.log',180)
    fresh()
    assert 'PASS rv32_program_tb' in text and 'data=0x53504c54' in text
    with trace.open(newline='') as stream:
        traps=[r for r in csv.DictReader(stream) if r['trap']=='1' and int(r['pc'],16)>=0x40000000]
    expected=[v for c in cases for v in [c['cause'],10 if c['mode']=='VS' else 9]]
    assert [int(r['cause']) for r in traps]==expected
    fault_traps=traps[::2]
    assert all(int(r['pc'],16)==0x40000ffe and int(r['tval'],16)==0x40001000 for r in fault_traps)
    dump(folder/'report.json',dict(passed=True,
        scope='S/VS second-parcel instruction page/access/guest-page faults with precise xepc/xtval, shifted guest PA, delegation, GVA and trap returns',
        model=model,runtime_inputs=runtime,generator_sha256=sha(__file__),
        source_sha256=sha(source),elf_sha256=sha(elf),trace_sha256=sha(trace),
        cases_sha256=sha(folder/'cases.json'),case_count=len(cases),compile=compile_run,run=run,traps=traps))
    print('PASS split instruction fetch faults:',len(cases),'cases,',len(traps),'precise traps',flush=True)


if __name__=='__main__':
    main()

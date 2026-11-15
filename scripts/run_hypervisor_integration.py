"""Native M/HS/VS HLV/HSV/HLVX, guest scalar/FP/A/CBO/V memory and traps.

This functional ELF is separate from all fixed performance benchmarks.
"""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump,source_inputs
folder=ROOT/'out/rva23/hypervisor_integration';folder.mkdir(parents=True,exist_ok=True)
source=ROOT/'sw/tests/rv64_hypervisor_basic.S'
runtime_inputs={p:sha(ROOT/p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex','sw/benchmarks/coremark/rv32_tim.ld']}
files=(ROOT/'rtl/filelist.f').read_text().splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv','tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
params=['-GXLEN=64','-GHAS_V=1','-GHAS_H=1','-GHAS_MISALIGNED=1','-GHAS_D=1','-GHAS_ZFHMIN=1','-GHAS_ZFA=1',
    '-GHAS_ZAWRS=1','-GHAS_ZIMOP=1','-GHAS_ZCMOP=1','-GHAS_ZCB=1','-GHAS_SVINVAL=1','-GHAS_SSNPM=1',
    '-GHAS_CBO=1','-GHAS_A=1','-GHAS_B=1','-GHAS_ZICOND=1','-GHAS_SMODE=1','-GHAS_MMU=1']
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh_svinval_zicbom_zicboz_zvbb_zvfhmin','-mabi=lp64d',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none','-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
    path=folder/'model.json';inputs=source_inputs(files);model=None
    for candidate in [path,ROOT/'out/rva23/vector_integration/model.json']:
        old=json.loads(candidate.read_text(encoding='utf-8')) if candidate.exists() else None
        if old and old['inputs']==inputs and old['params']==params and sha(ROOT/old['binary'])==old['binary_sha256']:
            model=old;break
    if model is None:model=sim.build('rva23_hypervisor_core','rv32_program_tb',files,params)
    dump(path,model)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit','+timeout_cycles=4000000','+expected_exit_code=0'],folder/'simulation.log',240)
    for p,h in {**inputs,**runtime_inputs}.items():assert sha(ROOT/p)==h,p
    assert 'PASS rv32_program_tb' in text and 'data=0x48595031' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000 or r['trap']=='1' and 0x40000000<=int(r['pc'],16)<0x40100000]
    assert [int(r['cause']) for r in traps]==[10,22,22,10],traps
    dump(folder/'report.json',{'passed':True,'scope':'Native M/HS/VS with VS Sv39, G-stage Bare, HLV/HSV/HLVX, guest FP/A/CBO/V and virtual-instruction traps',
        'model':model,'source_sha256':sha(source),'generator_sha256':sha(__file__),'runtime_inputs':runtime_inputs,'elf_sha256':sha(elf),
        'trace_sha256':sha(trace),'run':run,'traps':traps})
    print('PASS native H M/HS/VS, guest scalar/FP/A/CBO/V, HLV/HSV/HLVX and traps',flush=True)

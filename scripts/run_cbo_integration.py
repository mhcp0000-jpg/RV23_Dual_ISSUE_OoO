"""CBO.ZERO block boundaries, coherent cache invalidation and CSR permissions."""
import csv,json,re
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/cbo';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/scalar/model.json').read_text())
assert '-GHAS_CBO=1' in model['params']
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imafc_zicbom_zicbop_zicboz_zicsr_zifencei','-mabi=lp64f',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld','sw/tests/rv64_cbo.S','-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=2000000','+expected_exit_code=0'],folder/'simulation.log',180)
    fresh();assert 'PASS rv32_program_tb' in text and 'data=0x43424f31' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert [int(r['cause']) for r in traps]==[2,2,7],traps
    stats={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',next(l for l in text.splitlines() if l.startswith('CACHE_PERF ')))}
    assert stats['full_d_discard']>0,stats # distinguishes actual invalidate from a decoded NOP
    report={'passed':True,'scope':'Integrated Zicbom/Zicboz, 64-byte boundaries, permissions, pointer masking and fault-free prefetch hints',
        'model_inputs':model['inputs'],'binary_sha256':model['binary_sha256'],
        'elf_sha256':sha(elf),'source_sha256':sha(ROOT/'sw/tests/rv64_cbo.S'),
        'run':run,'trace_sha256':sha(trace),'cache_stats':stats,'traps':traps}
    dump(folder/'report.json',report)
    print('PASS RV64 CBO block zero, actual D-cache invalidation, U permissions, pointer masking, prefetch hints',flush=True)

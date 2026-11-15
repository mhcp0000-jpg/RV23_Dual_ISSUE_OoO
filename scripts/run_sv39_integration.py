"""Execute real S-mode virtual memory with precise pre-commit page faults."""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/sv39';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/scalar/model.json').read_text())
assert '-GHAS_MMU=1' in model['params']
rom='tb/fixtures/bootrom/bootrom_host_jump64.hex'
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imfc_zicsr_zifencei','-mabi=lp64f',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld','sw/tests/rv64_sv39.S','-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=2000000','+expected_exit_code=0'],folder/'simulation.log',180)
    fresh();assert 'PASS rv32_program_tb' in text and 'data=0x53563339' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000 or
           (r['trap']=='1' and 0x40000000<=int(r['pc'],16)<0x50000000)]
    assert [int(r['cause']) for r in traps]==[15,13,13,12,13,13,12],traps
    assert [int(r['tval'],16) for r in traps]==[
        0x40004000,0x40005000,0x40006000,0x40007000,0x40008000,0x40009000,0x40008000]
    report={'passed':True,'scope':'Integrated Sv39/Svade/PBMT/NAPOT, SRET, SFENCE remapping; G-stage integration remains pending',
        'model_inputs':model['inputs'],'binary':model['binary'],'binary_sha256':model['binary_sha256'],
        'elf':elf.relative_to(ROOT).as_posix(),'elf_sha256':sha(elf),'source_sha256':sha(ROOT/'sw/tests/rv64_sv39.S'),
        'runtime_inputs':{rom:sha(ROOT/rom)},'run':run,'trace_sha256':sha(trace),
        'traps':[{k:r[k] for k in ['pc','instruction','cause','tval']} for r in traps]}
    dump(folder/'report.json',report)
    print('PASS RV64 Sv39 actual page faults, unchanged read-only store target, A/D software fault, SUM/MXR, SFENCE remap, NAPOT/PBMT',flush=True)

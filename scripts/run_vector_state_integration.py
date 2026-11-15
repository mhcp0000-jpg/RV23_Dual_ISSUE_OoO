"""Architectural vector CSR, VS/FS/SD permissions and precise illegal traps."""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/vector_state';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/vector_integration/model.json').read_text())
assert '-GHAS_V=1' in model['params']
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
source=ROOT/'sw/tests/rv64_vector_state.S'
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcv_zvbb_zvfhmin','-mabi=lp64d','-nostdlib','-nostartfiles',
        '-Wl,--no-relax','-Wl,--build-id=none','-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit','+timeout_cycles=4000000','+expected_exit_code=0'],folder/'simulation.log',240)
    fresh();assert 'PASS rv32_program_tb' in text and 'data=0x56535431' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert [int(r['cause']) for r in traps]==[2]*11,traps
    dump(folder/'report.json',{'passed':True,'scope':'Integrated vector CSR WARL/read-only, VS/FS/SD, flags, FRM/VL0 illegal traps, retained payload',
        'model_inputs':model['inputs'],'binary_sha256':model['binary_sha256'],'elf_sha256':sha(elf),'source_sha256':sha(source),
        'generator_sha256':sha(__file__),'run':run,'trace_sha256':sha(trace),'traps':traps})
    print('PASS full-core vector CSR, VS/FS/SD state and eleven precise illegal traps',flush=True)

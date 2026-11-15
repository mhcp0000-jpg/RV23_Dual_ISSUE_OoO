"""Architectural FP state, mixed memory formats, compressed D and precise traps."""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/fp_state';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/scalar/model.json').read_text())
assert '-GHAS_D=1' in model['params']
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imafdc_zfhmin_zfa_zicsr_zifencei','-mabi=lp64d',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld','sw/tests/rv64_fp_state.S','-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=2000000','+expected_exit_code=0'],folder/'simulation.log',180)
    fresh();assert 'PASS rv32_program_tb' in text and 'data=0x46505354' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert [int(r['cause']) for r in traps]==[2]*7,traps
    compressed=[r for r in rows if int(r['instruction'],16)&3!=3]
    assert len(compressed)>=6,compressed
    dump(folder/'report.json',{'passed':True,'scope':'64-bit FP memory/boxing, compressed D, precise illegal traps, FS/SD state',
        'model_inputs':model['inputs'],'binary_sha256':model['binary_sha256'],
        'elf_sha256':sha(elf),'source_sha256':sha(ROOT/'sw/tests/rv64_fp_state.S'),
        'generator_sha256':sha(__file__),'run':run,'trace_sha256':sha(trace),
        'compressed_retirements':len(compressed),'traps':traps})
    print('PASS integrated FP state, memory boxing, compressed D and seven precise illegal traps',flush=True)

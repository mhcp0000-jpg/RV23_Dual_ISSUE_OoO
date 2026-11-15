"""Full-core FP16/32/64 memory operations with real Sv39 permission checks."""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/fp_sv39';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/scalar/model.json').read_text())
assert '-GHAS_D=1' in model['params'] and '-GHAS_MMU=1' in model['params']
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
template=ROOT/'sw/tests/rv64_atomic_sv39.S';body=ROOT/'sw/tests/rv64_fp_sv39_body.S'
text=template.read_text();header=text[:text.index('s_entry:')]
assert header.count('  li t0,0x800\n')==1
header=header.replace('  li t0,0x800\n','  li t0,0x6800\n')
source=folder/'test.S';source.write_text(header+body.read_text()+text[text.index('s_trap:'):])
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imafdc_zfhmin_zfa_zicsr_zifencei','-mabi=lp64d',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=2000000','+expected_exit_code=0'],folder/'simulation.log',180)
    fresh();assert 'PASS rv32_program_tb' in text and 'data=0x4650564d' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert [int(r['cause']) for r in traps]==[15]*4+[13]*4,traps
    assert [int(r['tval'],16) for r in traps]==[0x40004000]*3+[0x40005000]+[0x40006000]*3+[0x40008000]
    dump(folder/'report.json',{'passed':True,'scope':'FP16/32/64 memory format, real Sv39 W/D/SUM checks, no denied-store side effects',
        'model_inputs':model['inputs'],'binary_sha256':model['binary_sha256'],
        'elf_sha256':sha(elf),'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [template,body,source]},
        'generator_sha256':sha(__file__),'run':run,'trace_sha256':sha(trace),'traps':traps})
    print('PASS integrated FP Sv39 H/S/D loads/stores, W/D/SUM faults before side effects',flush=True)

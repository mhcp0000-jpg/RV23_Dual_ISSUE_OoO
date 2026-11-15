"""Native VS vectored interrupts, virtual timer/time offset and VU permissions.

Uses the exact H-enabled SoC model built by run_hypervisor_integration.py.
This is a functional ELF; no performance benchmark input is changed.
"""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump,source_inputs

folder=ROOT/'out/rva23/hypervisor_interrupt_integration'
folder.mkdir(parents=True,exist_ok=True)
source=ROOT/'sw/tests/rv64_hypervisor_interrupts.S'
runtime_inputs={p:sha(ROOT/p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex','sw/benchmarks/coremark/rv32_tim.ld']}
model=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text())
assert '-GHAS_H=1' in model['params'] and '-GXLEN=64' in model['params']
for p,h in {**model['inputs'],**runtime_inputs}.items():assert sha(ROOT/p)==h,p
assert sha(ROOT/model['binary'])==model['binary_sha256']

with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    compile_record,_=sim.run([GCC/'riscv-none-elf-gcc.exe',
        '-march=rv64gcvh_svinval_zicbom_zicboz_zvbb_zvfhmin','-mabi=lp64d',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=4000000','+expected_exit_code=0'],folder/'simulation.log',240)
    for p,h in {**model['inputs'],**runtime_inputs}.items():assert sha(ROOT/p)==h,p
    assert 'PASS rv32_program_tb' in text and 'data=0x48595033' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x40000000]
    assert [int(r['cause']) for r in traps]==[10,2,6,22,22,8],traps
    dump(folder/'report.json',{'passed':True,
        'scope':'Native HS/VS/VU, delegated injected VS software interrupt and offset Sstc timer, vectored VS trap cause renumbering, VU virtual-instruction permissions',
        'model':model,'source_sha256':sha(source),'generator_sha256':sha(__file__),'runtime_inputs':runtime_inputs,
        'elf_sha256':sha(elf),'trace_sha256':sha(trace),'compile':compile_record,'run':run,'traps':traps})
print('PASS native VS vectored software/timer interrupts, time offset and VU permissions',flush=True)

"""Native guest vector partial faults/restart plus AMO/CBO G-stage faults.

Uses the exact H-enabled SoC model built by run_hypervisor_integration.py.
This is a functional ELF; no performance benchmark input is changed.
"""
import argparse
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump,source_inputs

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--vu', action='store_true', help='Exercise the vector store/load restart in VU')
args = parser.parse_args()
folder=ROOT/('out/rva23/hypervisor_vector_faults_vu' if args.vu else 'out/rva23/hypervisor_vector_faults')
folder.mkdir(parents=True,exist_ok=True)
base=ROOT/'sw/tests/rv64_hypervisor_vector_faults.S'
source=base
runtime_inputs={p:sha(ROOT/p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex','sw/benchmarks/coremark/rv32_tim.ld']}
if args.vu:
    assembly = base.read_text(encoding='utf-8')
    replacements = [
        ('  li t0,0xcf\n', '  li t0,0xdf\n'),
        ('  li t0,(0x20000000 >> 2) | 0xcf\n', '  li t0,(0x20000000 >> 2) | 0xdf\n'),
        ('  li t0,0x180\n  csrw hstatus,t0\n  li t0,0x2300',
         '  li t0,0x80\n  csrw hstatus,t0\n  li t0,0x2200'),
        ('  li t1,0x180\n  bne t0,t1,fail', '  li t1,0x80\n  bne t0,t1,fail'),
        ('  li t1,10\n  beq t0,t1,guest_call', '  li t1,8\n  beq t0,t1,guest_call'),
        ('  li t0,7\n  bne s6,t0,fail', '  li t0,4\n  bne s6,t0,fail'),
    ]
    for original, replacement in replacements:
        assert assembly.count(original) == 1, original
        assembly = assembly.replace(original, replacement)
    amo_start = assembly.index('  li s7,3\n  li a0,0\n  ecall')
    final_call = assembly.index('  li s7,6\n  li a0,1\n  ecall', amo_start)
    assembly = assembly[:amo_start] + assembly[final_call:]
    source = folder / 'test.S'
    source.write_text(assembly, encoding='utf-8')
    runtime_inputs[base.relative_to(ROOT).as_posix()] = sha(base)
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
    assert 'PASS rv32_program_tb' in text and 'data=0x48595035' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x40000000]
    assert [int(r['cause']) for r in traps]==([23,8,21,8] if args.vu else [23,10,21,10,23,23,10]),traps
    retries = []
    for trap in (traps[0], traps[2]):
        assert int(trap['tval'],16) == 0x400a4000, trap
        retry, = (r for r in rows if r['trap'] == '0' and r['pc'] == trap['pc'] and
                  r['instruction'] == trap['instruction'] and int(r['order']) > int(trap['order']))
        retries.append(retry)
    dump(folder/'report.json',{'passed':True,
        'scope':('VU vector partial store/load faults, G-stage metadata and same-PC vstart restart' if args.vu else
                 'VS vector partial store/load faults and restart, AMO/CBO G-stage store faults'),
        'model':model,'source_sha256':sha(source),'generator_sha256':sha(__file__),'runtime_inputs':runtime_inputs,
        'elf_sha256':sha(elf),'trace_sha256':sha(trace),'compile':compile_record,'run':run,'traps':traps,'retries':retries})
print('PASS native VU vector partial store/load restart' if args.vu else
      'PASS native VS vector partial faults/restart and AMO/CBO G-stage metadata',flush=True)

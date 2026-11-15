"""Unaligned accesses across nonadjacent pages with pre-write permission faults."""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/misaligned_sv39';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/scalar/model.json').read_text())
assert '-GHAS_MISALIGNED=1' in model['params'] and '-GHAS_MMU=1' in model['params']
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
template=ROOT/'sw/tests/rv64_atomic_sv39.S';body=ROOT/'sw/tests/rv64_misaligned_sv39_body.S'
text=template.read_text();header=text[:text.index('s_entry:')]
header=header.replace('  li t0,0x800\n','  li t0,0x6800\n')
assert header.count('  li t0,0xb080\n')==1
header=header.replace('  li t0,0xb080\n','  li t0,0xb0a0\n') # also delegate load access fault
anchor='  la t0,root\n'
assert header.count(anchor)==1
header=header.replace(anchor,'''  la t1,level0
  li t0,(0x80036000 >> 2) | 0xc7
  sd t0,32(t1)
  li t0,0x80030ff8
  li t1,0x1122334455667788
  sd t1,0(t0)
  li t0,0x80036000
  li t1,0x8877665544332211
  sd t1,0(t0)
'''+anchor)
source=folder/'test.S';source.write_text(header+body.read_text()+text[text.index('s_trap:'):])
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imafdc_zfhmin_zicsr_zifencei','-mabi=lp64d',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=2000000','+expected_exit_code=0'],folder/'simulation.log',180)
    fresh();assert 'PASS rv32_program_tb' in text and 'data=0x4d495356' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert [int(r['cause']) for r in traps]==[15,15,13,7,5],traps
    assert [int(r['tval'],16) for r in traps]==[0x40004000]*5
    dump(folder/'report.json',{'passed':True,'scope':'Cross-page misalignment with nonadjacent PA, W/D/invalid/PBMT faults before writes, preserved FP destination',
        'model_inputs':model['inputs'],'binary_sha256':model['binary_sha256'],
        'elf_sha256':sha(elf),'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [template,body,source]},
        'generator_sha256':sha(__file__),'run':run,'trace_sha256':sha(trace),'traps':traps})
    print('PASS misaligned Sv39 cross-page translation, W/D/PBMT prevalidation, precise tval and FP destination',flush=True)

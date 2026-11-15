"""Full-core S-mode vector faults, nonadjacent PAs and same-PC restart."""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/vector_sv39';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/vector_integration/model.json').read_text())
assert '-GHAS_V=1' in model['params']
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
template=ROOT/'sw/tests/rv64_atomic_sv39.S';body=ROOT/'sw/tests/rv64_vector_sv39_body.S'
text=template.read_text();header=text[:text.index('s_entry:')]
header=header.replace('  li t0,0x800\n','  li t0,0x2a00\n') # MPP=S, FS=Initial, VS=Initial
header=header.replace('  li t0,0xb080\n','  li t0,0xb0a0\n')
anchor='  la t0,root\n';assert header.count(anchor)==1
header=header.replace(anchor,'''  la t1,level0
  li t0,(0x80036000 >> 2) | 0xc7
  sd t0,32(t1)
  li t0,0x80030ff0
  li t1,11
  sd t1,0(t0)
  li t1,22
  sd t1,8(t0)
  li t0,0x80036000
  li t1,33
  sd t1,0(t0)
  li t1,44
  sd t1,8(t0)
'''+anchor)
source=folder/'test.S';source.write_text(header+body.read_text())
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcv_zvbb_zvfhmin','-mabi=lp64d','-nostdlib','-nostartfiles',
        '-Wl,--no-relax','-Wl,--build-id=none','-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit','+timeout_cycles=4000000','+expected_exit_code=0'],folder/'simulation.log',240)
    fresh();assert 'PASS rv32_program_tb' in text and 'data=0x56535631' in text
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert [int(r['cause']) for r in traps]==[15,13,13,5],traps
    assert [int(r['tval'],16) for r in traps]==[0x40004000]*4
    dump(folder/'report.json',{'passed':True,'scope':'Integrated S-mode V memory, partial destination/state, vstart same-PC replay, FF, W/PBMT faults',
        'model_inputs':model['inputs'],'binary_sha256':model['binary_sha256'],'elf_sha256':sha(elf),
        'source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in [template,body,source]},
        'generator_sha256':sha(__file__),'run':run,'trace_sha256':sha(trace),'traps':traps})
    print('PASS full-core Sv39 vector page faults, exact restart, partial state and fault-only-first',flush=True)

"""Pending PLIC interrupt during a vector divide with younger scalar execution."""
import json,re,subprocess
from sim_runner import ROOT,Simulator,GCC,dump,sha,source_inputs

folder=ROOT/'out/rva23/vector_scalar_irq';folder.mkdir(parents=True,exist_ok=True)
source='sw/tests/rv64_vector_scalar_irq.S';linker='scripts/reference/upstream_htif.ld'
files=(ROOT/'rtl/filelist.f').read_text().splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/rv32_program_tb.sv','tb/rv23_vector_scalar_irq_tb.sv','tb/e2e/dpi/elf_loader.cpp']
inputs=source_inputs([source,linker,'tb/fixtures/bootrom/bootrom_host_jump64.hex'])
with Simulator() as sim:
    elf=folder/'test.elf';trace=folder/'commit.csv'
    compile_run,_=sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh','-mabi=lp64d',
        '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T',linker,source,'-o',elf],folder/'compile.log',60)
    symbols=subprocess.check_output([str(GCC/'riscv-none-elf-nm.exe'),'-n',str(elf)],text=True)
    pc=int(re.search(r'^([\da-f]+) \w irq_vector$',symbols,re.M)[1],16)
    model_path=folder/'model.json'
    prior_path=model_path if model_path.exists() else folder/'report.json'
    prior=json.loads(prior_path.read_bytes()) if prior_path.exists() else None
    model=prior.get('model',prior) if prior else None
    if not model or model['inputs']!=source_inputs(files) or sha(ROOT/model['binary'])!=model['binary_sha256']:
        model=sim.build('rv23_vector_scalar_irq','rv23_vector_scalar_irq_tb',files)
    dump(model_path,model)
    run,log=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}',f'+irq_pc={pc:x}',
        '+quiet_commit','+htif','+timeout_cycles=100000','+expected_exit_code=0'],folder/'simulation.log',120)
assert 'PASS rv32_program_tb' in log and inputs==source_inputs(inputs)
m=re.search(r'VECTOR_SCALAR_IRQ start=(\d+) pending=(\d+) retire=(\d+) trap=(\d+) overlap=(\d+)',log)
assert m
start,pending,retire,trap,overlap=map(int,m.groups())
assert start<pending<retire<trap and overlap>0
dump(folder/'report.json',dict(passed=True,scope='Directed native non-memory vector IRQ boundary with scalar overlap, PLIC claim and result checks; not an exhaustive interrupt proof',
    driver_sha256=sha(__file__),model=model,inputs=inputs,elf_sha256=sha(elf),
    trace_sha256=sha(trace),compile=compile_run,run=run,
    cycles=dict(start=start,pending=pending,retire=retire,trap=trap),scalar_overlap=overlap))
print('PASS non-memory vector/scalar overlap preserves precise PLIC interrupt boundary',start,pending,retire,trap,overlap,flush=True)

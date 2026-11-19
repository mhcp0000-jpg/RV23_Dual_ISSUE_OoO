"""Observe real vector/memory FSM occupancy on an unchanged saved CoreMark ELF."""
import json,re,subprocess
from sim_runner import ROOT,Simulator,GCC,dump,sha,source_inputs

folder=ROOT/'out/performance/vector_occupancy';folder.mkdir(parents=True,exist_ok=True)
expected_path=ROOT/'out/performance/vector_batch/coremark_2.json'
expected=json.loads(expected_path.read_bytes());assert expected['passed']
native=expected['model'];assert native['inputs']==source_inputs(native['inputs'])
elf=ROOT/'out/performance/rv64_coremark/o3_rvv_2/coremark.elf'
assert sha(elf)==expected['elf_sha256']
symbols=subprocess.check_output([str(GCC/'riscv-none-elf-nm.exe'),'-n',str(elf)],text=True)
pcs={name:int(re.search(r'^([\da-f]+) \w '+name+'$',symbols,re.M)[1],16) for name in ['start_time','stop_time']}
files=(ROOT/'rtl/filelist.f').read_text().splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp','tb/rv23_vector_performance_tb.sv']
assert {p:h for p,h in source_inputs(files).items() if p!='tb/rv23_vector_performance_tb.sv'}==native['inputs']
with Simulator() as sim:
    model_path=folder/'model.json'
    model=json.loads(model_path.read_bytes()) if model_path.exists() else None
    if not model or model['inputs']!=source_inputs(files) or sha(ROOT/model['binary'])!=model['binary_sha256']:
        model=sim.build('rv23_vector_performance','rv23_vector_performance_tb',files)
        dump(model_path,model)
    run,log=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+profile_start_pc={pcs["start_time"]:x}',f'+profile_stop_pc={pcs["stop_time"]:x}',
        '+quiet_commit','+timeout_cycles=20000000','+expected_exit_code=0'],folder/'simulation.log',2500)
assert 'PASS rv32_program_tb' in log
words=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]',log)]
packet=words[words.index(0x434d0001):][:12]
assert packet==expected['packet'],'Observer changed the benchmark result/cycles'
m=re.search(r'^VECTOR_PROFILE (.+)$',log,re.M);assert m
summary={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',m[1])}
names=['IDLE','CHECK','ELEMENT','GATHER','FINISH','RESULT','FP_REQUEST','FP_WAIT','MEM_ISSUE','MEM_WAIT',
       'INT_DRAIN','INT_REDUCE_WAIT','DIV_REQUEST','DIV_WAIT','WB_DRAIN','UNUSED']
states=[dict(name=names[int(s)],cycles=int(c),no_retire_cycles=int(e)) for s,c,e in
        re.findall(r'^VECTOR_PROFILE_STATE index=(\d+) cycles=(\d+) empty=(\d+)',log,re.M)]
mem_names=['IDLE','TRANSLATE','WAIT_TRANSLATE','CHECK','MEMORY_REQUEST','MEMORY_RESPONSE','RESULT','UNUSED']
memory=[dict(name=mem_names[int(s)],cycles=int(c)) for s,c in
        re.findall(r'^VECTOR_PROFILE_MEMORY index=(\d+) cycles=(\d+)',log,re.M)]
assert len(states)==16 and len(memory)==8
assert sum(s['cycles'] for s in states)==summary['cycles']
assert sum(s['no_retire_cycles'] for s in states)==summary['empty']
assert sum(s['cycles'] for s in memory)==states[9]['cycles']
assert summary['requests']==summary['responses']>0
assert model['inputs']==source_inputs(model['inputs']) and sha(elf)==expected['elf_sha256']
dump(folder/'report.json',dict(passed=True,scope='Read-only full-core observer; retire-delimited start_time/stop_time window. Occupancy and overlapping no-retire counts are observations, not exclusive causal stall ownership.',
    model=model,run=run,driver_sha256=sha(__file__),elf_sha256=sha(elf),
    expected_report_sha256=sha(expected_path),packet=packet,pcs=pcs,
    summary=summary,vector_states=states,memory_states=memory))
print('PASS vector occupancy observer preserves exact quiet CoreMark packet',summary,flush=True)
for state in sorted(states,key=lambda s:s['cycles'],reverse=True):print(state,flush=True)
for state in memory:print('memory',state,flush=True)

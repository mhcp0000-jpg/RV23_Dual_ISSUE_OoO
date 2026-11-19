"""Observe actual vector hits on shared D-cache using the fixed alias ELF."""
import json
import re
from run_scalar_vector_memory import verify_traces
from sim_runner import ROOT, Simulator, dump, sha, source_inputs

folder=ROOT/'out/rva23/vector_shared_cache';folder.mkdir(parents=True,exist_ok=True)
original=ROOT/'out/rva23/scalar_vector_memory'
old=json.loads((original/'report.json').read_bytes());assert old['passed']
elf=original/'test.elf';sail=original/'sail.csv'
assert sha(elf)==old['elf_sha256'] and sha(sail)==old['sail_trace_sha256']
model=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_bytes())
assert model['inputs']==source_inputs(model['inputs']) and sha(ROOT/model['binary'])==model['binary_sha256']
trace=folder/'commit.csv'
with Simulator() as sim:
    run,log=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit','+htif',
        '+vector_cache_trace','+timeout_cycles=1000000','+expected_exit_code=0'],folder/'simulation.log',120)
outcomes=verify_traces(sail,trace)
m=re.search(r'VECTOR_CACHE reads=(\d+) writes=(\d+) hits=(\d+) data_read_beats=(\d+)',log)
assert m
reads,writes,hits,beats=map(int,m.groups())
assert (reads,writes)==(48,16) and 0<hits<=reads and beats>0
dump(folder/'report.json',dict(passed=True,scope='Native scalar/vector SRAM/Sv39 aliases on shared D-cache; 64-bit element requests, not 128-bit vector memory batching or all coherence races',
    model=model,run=run,elf=elf.relative_to(ROOT).as_posix(),elf_sha256=sha(elf),sail_trace_sha256=sha(sail),
    trace_sha256=sha(trace),driver_sha256=sha(__file__),helper_sha256=sha(ROOT/'scripts/run_scalar_vector_memory.py'),
    outcomes=outcomes,reads=reads,writes=writes,hits=hits,data_read_beats=beats))
print('PASS native shared vector D-cache',outcomes,dict(reads=reads,writes=writes,hits=hits,data_read_beats=beats))

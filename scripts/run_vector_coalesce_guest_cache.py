"""Observe the existing VS Sv39 VLE32/VSE32 fixture on shared D-cache."""
import json,re
from sim_runner import ROOT,Simulator,sha,dump,source_inputs

native_path=ROOT/'out/rva23/hypervisor_integration/report.json'
native=json.loads(native_path.read_bytes());assert native['passed']
model=native['model'];assert model['inputs']==source_inputs(model['inputs'])
assert sha(ROOT/model['binary'])==model['binary_sha256']
runtime=source_inputs(['sw/tests/rv64_hypervisor_basic.S','tb/fixtures/bootrom/bootrom_host_jump64.hex'])
assert runtime['sw/tests/rv64_hypervisor_basic.S']==native['source_sha256']
elf=ROOT/'out/rva23/hypervisor_integration/test.elf';elf_hash=sha(elf)
folder=ROOT/'out/rva23/vector_coalesce_guest_cache'
with Simulator() as sim:
    run,log=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        '+quiet_commit','+vector_cache_trace','+timeout_cycles=100000','+expected_exit_code=0'],folder/'simulation.log',120)
assert 'PASS rv32_program_tb' in log and 'data=0x48595031' in log
m=re.search(r'VECTOR_CACHE reads=(\d+) writes=(\d+) hits=(\d+) data_read_beats=(\d+)',log);assert m
reads,writes,hits,beats=map(int,m.groups())
assert reads==2 and writes==4 and hits>0,(reads,writes,hits)
assert sha(elf)==elf_hash and runtime==source_inputs(runtime)
assert model['inputs']==source_inputs(model['inputs'])
dump(folder/'report.json',dict(passed=True,
    scope='Existing VS Sv39 guest VLE32/VSE32: two 64-bit shared-cache reads for four 32-bit load elements; stores keep four element requests. Not all coherence/fault races.',
    driver_sha256=sha(__file__),native_report_sha256=sha(native_path),runtime_inputs=runtime,
    model=model,run=run,elf_sha256=elf_hash,reads=reads,writes=writes,hits=hits))
print('PASS native guest coalesced shared D-cache',reads,writes,hits,flush=True)

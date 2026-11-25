"""Compare the exact saved 10-iteration CoreMark ELFs on current vector RTL."""
import json
import re
from sim_runner import ROOT, Simulator, dump, sha, source_inputs

folder=ROOT/'out/performance/vector_pipeline_replay';folder.mkdir(parents=True,exist_ok=True)
baseline_path=ROOT/'out/performance/rv64_coremark/report.json'
baseline=json.loads(baseline_path.read_bytes());assert baseline['passed']
model=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_bytes())
assert model['params']==baseline['model']['params'] and model['inputs']==source_inputs(model['inputs'])
assert sha(ROOT/model['binary'])==model['binary_sha256']
selected=[c for c in baseline['cases'] if c['iterations']==10]
assert {c['variant'] for c in selected}=={'o2_scalar','o3_scalar','o3_rvv'} and len(selected)==3
report=dict(passed=False,certified_score=False,scope='Exact saved RV64 CoreMark ELFs, ten iterations; historical baseline versus current RTL, no ELF rebuild and no physical-clock score',
    baseline_sha256=sha(baseline_path),model=model,driver_sha256=sha(__file__),cases=[])
dump(folder/'report.json',report)
with Simulator() as sim:
    for old in selected:
        variant=old['variant'];elf=ROOT/f'out/performance/rv64_coremark/{variant}_10/coremark.elf'
        assert sha(elf)==old['elf_sha256'] and '-DITERATIONS=10' in old['flags']
        assert sha(ROOT/old['run']['log'])==old['run']['log_sha256']
        run,log=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            '+quiet_commit','+timeout_cycles=100000000','+expected_exit_code=0'],folder/f'{variant}.log',5000)
        assert 'PASS rv32_program_tb' in log and 'ELF AXI readback PASS' in log
        values=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]',log)]
        start=values.index(0x434d0001);packet=values[start:start+12]
        assert len(packet)==12 and packet[1]==10 and packet[6:10]==[0xe9f5,0xe714,0x1fd7,0x8e3a] and packet[11]&0x17==1
        assert sha(elf)==old['elf_sha256'] and model['inputs']==source_inputs(model['inputs'])
        cycles=packet[2]+(packet[3]<<32);instructions=packet[4]+(packet[5]<<32)
        assert instructions==old['instructions'],(variant,instructions,old['instructions'])
        result=dict(variant=variant,iterations=10,elf=elf.relative_to(ROOT).as_posix(),elf_sha256=sha(elf),
            run=run,packet=packet,cycles=cycles,instructions=instructions,ipc=instructions/cycles,
            coremark_per_mhz_estimate=10000000/cycles,baseline_cycles=old['cycles'],baseline_ipc=old['ipc'],
            cycle_ratio=cycles/old['cycles'])
        report['cases'].append(result);dump(folder/'report.json',report)
        print('PASS exact-ELF CoreMark',variant,dict(cycles=cycles,ipc=result['ipc'],ratio=result['cycle_ratio']),flush=True)
report['passed']=True;dump(folder/'report.json',report)

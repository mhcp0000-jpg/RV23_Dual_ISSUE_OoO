"""Replay an unchanged ten-iteration ELF against the saved pre-fastpath measurement."""
import argparse,json,re
from sim_runner import ROOT, Simulator, dump, sha, source_inputs

parser=argparse.ArgumentParser()
parser.add_argument('--variant',choices=['o2_scalar','o3_scalar','o3_rvv'],default='o3_rvv')
args=parser.parse_args()
folder=ROOT/'out/performance/vector_fastpath';folder.mkdir(parents=True,exist_ok=True)
before_path=ROOT/'out/performance/vector_fastpath_before/coremark_10.json'
before=json.loads(before_path.read_bytes());assert before['passed']
old=next(c for c in before['cases'] if c['variant']==args.variant)
assert old['iterations']==10 and sha(ROOT/old['run']['log'])==old['run']['log_sha256']
model=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_bytes())
assert model['params']==before['model']['params'] and model['inputs']==source_inputs(model['inputs'])
assert sha(ROOT/model['binary'])==model['binary_sha256']
elf=ROOT/old['elf'];assert sha(elf)==old['elf_sha256']
report=dict(passed=False,certified_score=False,variant=args.variant,iterations=10,
    scope='Exact ELF before/after aligned preflight and vector completion-drain optimization; no physical clock claim',
    before_report_sha256=sha(before_path),before=old,model=model,elf_sha256=sha(elf),driver_sha256=sha(__file__))
dest=folder/(args.variant+'.json');dump(dest,report)
with Simulator() as sim:
    run,log=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        '+quiet_commit','+timeout_cycles=100000000','+expected_exit_code=0'],folder/(args.variant+'.log'),5000)
assert 'PASS rv32_program_tb' in log and 'ELF AXI readback PASS' in log
values=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]',log)]
start=values.index(0x434d0001);packet=values[start:start+12]
assert len(packet)==12 and packet[1]==10 and packet[6:10]==[0xe9f5,0xe714,0x1fd7,0x8e3a] and packet[11]&0x17==1
assert sha(elf)==old['elf_sha256'] and model['inputs']==source_inputs(model['inputs'])
cycles=packet[2]+(packet[3]<<32);instructions=packet[4]+(packet[5]<<32)
assert instructions==old['instructions'],(instructions,old['instructions'])
report.update(passed=True,run=run,packet=packet,cycles=cycles,instructions=instructions,
    ipc=instructions/cycles,coremark_per_mhz_estimate=10000000/cycles,
    cycle_reduction_percent=100*(old['cycles']-cycles)/old['cycles'],speedup=old['cycles']/cycles)
dump(dest,report)
print('PASS exact-ELF CoreMark 10',args.variant,'cycles',cycles,'IPC',report['ipc'],
      'cycle reduction %',report['cycle_reduction_percent'],'speedup',report['speedup'],flush=True)

"""Attribute retire gaps on the same saved two-iteration RVV ELF before/after."""
import argparse,collections,csv,json,re
from sim_runner import ROOT,Simulator,dump,sha,source_inputs

parser=argparse.ArgumentParser()
parser.add_argument('mode',choices=['before','after'])
args=parser.parse_args()
folder=ROOT/'out/performance/vector_fastpath_profile';folder.mkdir(parents=True,exist_ok=True)
prior=json.loads((ROOT/'out/performance/rv64_coremark/report.json').read_bytes())
old=next(c for c in prior['cases'] if c['variant']=='o3_rvv' and c['iterations']==2)
saved=ROOT/'out/performance/vector_fastpath_before'
before=json.loads((saved/'model.json').read_bytes())
current=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_bytes())
assert current['inputs']==source_inputs(current['inputs']) and current['params']==before['params']
changes={p for p,h in before['inputs'].items() if current['inputs'][p]!=h}
assert changes=={'rtl/backend/rv_vector_engine.sv','rtl/backend/rv23_hypervisor_memory_head.sv'},changes
for p in changes:assert sha(saved/p.rsplit('/',1)[-1])==before['inputs'][p]
model=before if args.mode=='before' else current
assert sha(ROOT/model['binary'])==model['binary_sha256']
elf=ROOT/'out/performance/rv64_coremark/o3_rvv_2/coremark.elf'
disassembly=elf.parent/'disassembly.txt';text=disassembly.read_text(encoding='utf-8')
assert sha(elf)==old['elf_sha256']
decoded={int(pc,16):op for pc,op in re.findall(r'^\s*([\da-f]+):\s+[\da-f]+\s+(\S+)',text,re.M)}
start_pc=int(re.search(r'^([\da-f]+) <start_time>:',text,re.M)[1],16)
stop_pc=int(re.search(r'^([\da-f]+) <stop_time>:',text,re.M)[1],16)
trace=folder/(args.mode+'.csv')
with Simulator() as sim:
    run,log=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
        '+timeout_cycles=20000000','+expected_exit_code=0'],folder/(args.mode+'.log'),2000)
assert 'PASS rv32_program_tb' in log
words=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]',log)]
packet=words[words.index(0x434d0001):][:12]
assert packet[1]==2 and packet[6:10]==[0xe9f5,0xe714,0x1fd7,0x8e3a] and packet[11]&0x17==1
cycles=packet[2]+(packet[3]<<32);instructions=packet[4]+(packet[5]<<32)
assert instructions==old['instructions'] and sha(elf)==old['elf_sha256']
mix=collections.Counter();gaps=collections.Counter();active=False;stopped=False;last=None
with trace.open(newline='') as stream:
    for row in csv.DictReader(stream):
        pc=int(row['pc'],16)
        if not active:active=pc==start_pc
        if not active:continue
        if pc==stop_pc:stopped=True;break
        assert row['trap']=='0'
        op=decoded[pc];cycle=int(row['cycle']);mix[op]+=1
        if last is not None:gaps[op]+=max(0,cycle-last-1)
        last=cycle
assert stopped and current['inputs']==source_inputs(current['inputs'])
dump(folder/(args.mode+'.json'),dict(passed=True,
    scope='Same two-iteration ELF. No-retire gaps attributed to next retired mnemonic; attribution is not causal stall ownership. Ten-iteration comparison is separate.',
    driver_sha256=sha(__file__),model=model,run=run,elf_sha256=sha(elf),
    trace_sha256=sha(trace),disassembly_sha256=sha(disassembly),packet=packet,
    cycles=cycles,instructions=instructions,ipc=instructions/cycles,
    instruction_mix=dict(mix),gap_attribution=dict(gaps)))
print('PASS exact-ELF RVV profile',args.mode,'cycles',cycles,'IPC',instructions/cycles,flush=True)
for op,n in gaps.most_common(15):print(op,'count',mix[op],'gap_attribution',n,flush=True)

"""Measure scalar/vector dispatch overlap on saved, unchanged performance ELFs."""
import argparse,json,re
from sim_runner import ROOT,Simulator,dump,sha,source_inputs

parser=argparse.ArgumentParser()
parser.add_argument('--coremark-iterations',type=int,choices=[2,10])
args=parser.parse_args()
folder=ROOT/'out/performance/vector_overlap';folder.mkdir(parents=True,exist_ok=True)
before=json.loads((ROOT/'out/performance/vector_overlap_before/model.json').read_bytes())
after=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_bytes())
assert after['inputs']==source_inputs(after['inputs']) and after['params']==before['params']
assert {p for p,h in before['inputs'].items() if after['inputs'][p]!=h}=={
    'rtl/backend/rv_decode2.sv','rtl/backend/rv_backend.sv'}
for model in [before,after]:assert sha(ROOT/model['binary'])==model['binary_sha256']
def words(log):return [int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]',log)]

if args.coremark_iterations:
    n=args.coremark_iterations
    baseline_path=ROOT/('out/performance/vector_fastpath_profile/after.json' if n==2 else
        'out/performance/vector_overlap_before/coremark_10.json')
    base=json.loads(baseline_path.read_bytes());assert base['passed']
    assert base['model']['binary_sha256']==before['binary_sha256']
    assert sha(ROOT/base['run']['log'])==base['run']['log_sha256']
    elf=ROOT/f'out/performance/rv64_coremark/o3_rvv_{n}/coremark.elf'
    assert sha(elf)==base['elf_sha256']
    dest=folder/f'coremark_{n}.json'
    report=dict(passed=False,certified_score=False,before_commit='a49f7a9',iterations=n,
        scope='Same unchanged RVV CoreMark ELF, non-memory vector dispatch overlap; no physical Fmax claim',
        before=base,baseline_report_sha256=sha(baseline_path),model=after,elf_sha256=sha(elf),driver_sha256=sha(__file__))
    dump(dest,report)
    with Simulator() as sim:
        run,log=sim.run([ROOT/after['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            '+quiet_commit','+timeout_cycles=100000000','+expected_exit_code=0'],folder/f'coremark_{n}.log',5000)
    packet=words(log);packet=packet[packet.index(0x434d0001):][:12]
    assert len(packet)==12 and packet[1]==n and packet[6:10]==[0xe9f5,0xe714,0x1fd7,0x8e3a] and packet[11]&0x17==1
    assert 'PASS rv32_program_tb' in log and sha(elf)==base['elf_sha256']
    cycles=packet[2]+(packet[3]<<32);instructions=packet[4]+(packet[5]<<32)
    assert instructions==base['instructions']
    assert after['inputs']==source_inputs(after['inputs'])
    report.update(passed=True,run=run,packet=packet,cycles=cycles,instructions=instructions,
        ipc=instructions/cycles,coremark_per_mhz_estimate=n*1000000/cycles,
        cycle_reduction_percent=100*(base['cycles']-cycles)/base['cycles'],speedup=base['cycles']/cycles)
    dump(dest,report)
    print('PASS same-ELF RVV CoreMark',n,'cycles',cycles,'IPC',report['ipc'],'cycle reduction %',report['cycle_reduction_percent'],flush=True)
else:
    prior=json.loads((ROOT/'out/performance/vector_latency/report.json').read_bytes())
    elf=ROOT/'out/performance/vector_latency/test.elf';assert sha(elf)==prior['elf_sha256']
    results={}
    with Simulator() as sim:
        for label,model in [('before',before),('after',after)]:
            run,log=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
                '+quiet_commit','+timeout_cycles=200000','+expected_exit_code=0'],folder/(label+'.log'),300)
            values=words(log)
            assert 'PASS rv32_program_tb' in log and values[::2]==list(range(0x564c4100,0x564c4100+len(prior['cases'])))
            results[label]=dict(model=model,run=run,cycles=values[1::2])
    assert results['before']['cycles']==[c['after_cycles'] for c in prior['cases']]
    assert results['after']['cycles'][0]==results['before']['cycles'][0]
    measured=[dict(name=c['name'],operations=128,before_cycles=a,after_cycles=b,
        cycle_reduction_percent=100*(a-b)/a) for c,a,b in zip(prior['cases'],results['before']['cycles'],results['after']['cycles'])]
    assert after['inputs']==source_inputs(after['inputs']) and sha(elf)==prior['elf_sha256']
    dump(folder/'latency.json',dict(passed=True,scope='Same warmed 128-instruction full-core ELF; not isolated FU latency',
        before_commit='a49f7a9',driver_sha256=sha(__file__),elf_sha256=sha(elf),results=results,cases=measured))
    for case in measured:print(case,flush=True)

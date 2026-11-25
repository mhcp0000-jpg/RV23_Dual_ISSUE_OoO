"""Check saved CoreMark ELF runs, RTL sources and raw logs for fetch fast path."""
import hashlib,json,re,subprocess
from sim_runner import ROOT,sha,source_inputs,dump

before=json.loads((ROOT/'out/performance/fetch_pipe_before/model.json').read_bytes())
after=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_bytes())
assert before['inputs'].keys()==source_inputs(before['inputs']).keys()
for p,h in before['inputs'].items():
    data=subprocess.check_output(['git','show','47466c3:'+p],cwd=ROOT)
    assert hashlib.sha256(data).hexdigest()==h,p
assert after['inputs']==source_inputs(after['inputs'])
changes={p for p in set(before['inputs'])|set(after['inputs'])
    if before['inputs'].get(p)!=after['inputs'].get(p)}
assert changes=={'rtl/soc/rv23_if_translate.sv'}
for p,h in before['inputs'].items():
    if p!='rtl/soc/rv23_if_translate.sv':assert sha(ROOT/p)==h,p
assert before['params']==after['params']
assert sha(ROOT/before['binary'])==before['binary_sha256']
assert sha(ROOT/after['binary'])==after['binary_sha256']
results={}
for n in [2,10]:
    report=json.loads((ROOT/f'out/performance/fetch_pipe/coremark_{n}.json').read_bytes())
    assert report['passed'] and report['model']['inputs']==after['inputs']
    assert report['model']['binary_sha256']==after['binary_sha256']
    for run in [report['run'],report['before']['run']]:
        assert run['passed'] and run['exit_code']==0
        assert sha(ROOT/run['log'])==run['log_sha256']
    elf=ROOT/f'out/performance/rv64_coremark/o3_rvv_{n}/coremark.elf'
    assert sha(elf)==report['elf_sha256']==report['before']['elf_sha256']
    values=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]',
        (ROOT/report['run']['log']).read_text())]
    packet=values[values.index(0x434d0001):][:12]
    assert packet==report['packet'] and packet[1]==n
    assert packet[6:10]==[0xe9f5,0xe714,0x1fd7,0x8e3a]
    assert report['instructions']==report['before']['instructions']
    results[str(n)]={k:report[k] for k in ['iterations','elf_sha256','cycles','instructions',
        'ipc','cycle_reduction_percent','coremark_per_mhz_estimate','packet','run']}
    results[str(n)]['before_cycles']=report['before']['cycles']
    results[str(n)]['before_ipc']=report['before']['ipc']
dump(ROOT/'docs/evidence/fetch_bare_fastpath.json',dict(passed=True,
    complete_profile_validation=False,physical_fmax_validated=False,before_commit='47466c3',
    source_changes=sorted(changes),before_model=before,after_model=after,coremark=results,
    scope='Same saved RVV CoreMark ELFs at 2 and 10 iterations; unchanged CRC/instruction count; native H/V integration and focused IF translation tests; not full profile, ACT/RV32 release, or physical timing sign-off.'))
print('PASS source-bound bare fetch fast-path audit',
      {n:round(r['cycle_reduction_percent'],4) for n,r in results.items()},flush=True)

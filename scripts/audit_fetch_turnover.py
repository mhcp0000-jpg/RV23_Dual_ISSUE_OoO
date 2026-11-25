"""Validate fixed-ELF turnover comparisons and baseline source provenance."""
import hashlib,json,re,subprocess
from sim_runner import ROOT,sha,source_inputs,dump
before=json.loads((ROOT/'out/performance/fetch_turnover_before/model.json').read_bytes())
after=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_bytes())
assert before['params']==after['params']
assert after['inputs']==source_inputs(after['inputs'])
changed={p for p in set(before['inputs'])|set(after['inputs'])
    if before['inputs'].get(p)!=after['inputs'].get(p)}
assert changed=={'rtl/soc/rv23_if_translate.sv'}
for p,h in before['inputs'].items():
    old=subprocess.check_output(['git','show','9964fe2:'+p],cwd=ROOT)
    assert hashlib.sha256(old).hexdigest()==h,p
assert sha(ROOT/before['binary'])==before['binary_sha256']
assert sha(ROOT/after['binary'])==after['binary_sha256']
results={}
for n in [2,10]:
    report=json.loads((ROOT/f'out/performance/fetch_turnover/coremark_{n}.json').read_bytes())
    assert report['passed'] and report['model']['inputs']==after['inputs']
    assert report['model']['binary_sha256']==after['binary_sha256']
    for run in [report['run'],report['before']['run']]:
        assert run['passed'] and run['exit_code']==0 and sha(ROOT/run['log'])==run['log_sha256']
    elf=ROOT/f'out/performance/rv64_coremark/o3_rvv_{n}/coremark.elf'
    assert sha(elf)==report['elf_sha256']==report['before']['elf_sha256']
    words=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]',
        (ROOT/report['run']['log']).read_text())]
    packet=words[words.index(0x434d0001):][:12]
    assert packet==report['packet'] and packet[1]==n and packet[6:10]==[0xe9f5,0xe714,0x1fd7,0x8e3a]
    assert report['instructions']==report['before']['instructions']
    results[str(n)]={k:report[k] for k in ['iterations','elf_sha256','cycles','instructions','ipc',
        'cycle_reduction_percent','coremark_per_mhz_estimate','packet','run']}
    results[str(n)]['before_cycles']=report['before']['cycles']
dump(ROOT/'docs/evidence/fetch_response_turnover.json',dict(passed=True,
    complete_profile_validation=False,physical_fmax_validated=False,before_commit='9964fe2',
    source_changes=sorted(changed),before_model=before,after_model=after,coremark=results,
    scope='Same saved RVV CoreMark ELFs at 2 and 10 iterations; unchanged CRC/instruction count; focused response-turnover and native H/V integration; no physical timing sign-off.'))
print('PASS source-bound fetch-turnover audit',
      {n:round(r['cycle_reduction_percent'],4) for n,r in results.items()},flush=True)

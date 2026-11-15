"""Compare the preserved whole-cache-invalidation run with the current SoC.

Requires identical CoreMark ELF, retired instruction count, iterations and CRC.
Counters cover the whole post-load program; CSR timing covers the benchmark.
"""
from pathlib import Path
import json,re
from sim_runner import ROOT,sha,dump

folder=ROOT/'out/performance'
before=json.loads((folder/'before/coremark_report.json').read_text())
after=json.loads((ROOT/'out/programs/report.json').read_text())
assert sha(ROOT/before['shared_elf'])==before['shared_elf_sha256']
for path,digest in before['model_inputs'].items():
    snapshot=folder/'before'/Path(path).name
    assert sha(snapshot if snapshot.exists() else ROOT/path)==digest,'Changed baseline input: '+path
for path,digest in after['model_inputs'].items():
    assert sha(ROOT/path)==digest,'Changed current input: '+path
def extract(report,log):
    case=next(c for c in report['cases'] if c['name']=='coremark')
    assert case['passed']
    text=log.read_text()
    assert sha(log)==case['run']['log_sha256']
    values=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([0-9a-fA-F]{8})\]',text)]
    start=values.index(0x434d0001)
    assert values[start:start+12]==case['coremark']['packet'],'Report/telemetry differ'
    match=re.search(r'CACHE_PERF (.*)',text)
    assert match,'Missing cache counters'
    return case,{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',match[1])}
b,bc=extract(before,folder/'before/coremark_simulation.log')
a,ac=extract(after,ROOT/'out/programs/coremark/simulation.log')
assert b['program']==a['program'],'Benchmark/software inputs changed'
assert sha(ROOT/a['program']['elf'])==before['shared_elf_sha256']
for key in ['instructions','iterations']:
    assert b['coremark'][key]==a['coremark'][key],key+' differs'
assert b['coremark']['packet'][6:10]==a['coremark']['packet'][6:10]
assert a['coremark']['cycles']<b['coremark']['cycles'],'No measured speedup'
result={'passed':True,'scope':'Same ELF, 2 iterations, same CRC and timed retired instructions; not certified CoreMark score',
    'shared_elf_sha256':before['shared_elf_sha256'],
    'before':{'coremark':b['coremark'],'whole_program_cache':bc,'model_inputs':before['model_inputs'],
              'log':'out/performance/before/coremark_simulation.log','log_sha256':b['run']['log_sha256']},
    'after':{'coremark':a['coremark'],'whole_program_cache':ac,'model_inputs':after['model_inputs'],
             'log':a['run']['log'],'log_sha256':a['run']['log_sha256']},
    'speedup':b['coremark']['cycles']/a['coremark']['cycles'],
    'cycle_reduction_percent':100*(1-a['coremark']['cycles']/b['coremark']['cycles'])}
dump(folder/'comparison.json',result)
print(json.dumps({k:result[k] for k in ['passed','speedup','cycle_reduction_percent']},indent=2))

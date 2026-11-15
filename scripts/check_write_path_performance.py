"""Bind the latest exact-ELF runs to the preserved banked write-path baseline."""
import json,re
from sim_runner import ROOT,sha,dump

archive=ROOT/'out/performance/wt_before'
baseline_path=archive/'out/performance/banked_after/report.json'
current_path=ROOT/'out/performance/banked_after/report.json'
before=json.loads(baseline_path.read_text());after=json.loads(current_path.read_text())
assert before['passed'] and after['passed']
baseline_model=json.loads((archive/'out/programs/model.json').read_text())
for p,h in baseline_model['inputs'].items():assert sha(archive/p)==h,p
assert sha(archive/baseline_model['binary'])==baseline_model['binary_sha256']
assert before['after_binary_sha256']==baseline_model['binary_sha256']
for p,h in after['after_model_inputs'].items():assert sha(ROOT/p)==h,p
current_model=json.loads((ROOT/'out/programs/model.json').read_text())
assert after['after_binary_sha256']==current_model['binary_sha256']==sha(ROOT/current_model['binary'])
result={'passed':False,'baseline_report':baseline_path.relative_to(ROOT).as_posix(),
        'baseline_report_sha256':sha(baseline_path),'current_report':current_path.relative_to(ROOT).as_posix(),
        'current_report_sha256':sha(current_path),'before_binary_sha256':baseline_model['binary_sha256'],
        'before_binary':(archive/baseline_model['binary']).relative_to(ROOT).as_posix(),
        'before_model_inputs':{(archive/p).relative_to(ROOT).as_posix():h for p,h in baseline_model['inputs'].items()},
        'after_binary_sha256':after['after_binary_sha256'],'after_model_inputs':after['after_model_inputs'],
        'scope':'Same ELF and CRC; two-bank cache before/after request and response fall-through; WT waits bus response.',
        'cases':[]}
for n in [2,10]:
    old=next(c for c in before['cases'] if c['iterations']==n)
    new=next(c for c in after['cases'] if c['iterations']==n)
    assert old['elf_sha256']==new['elf_sha256']==sha(ROOT/new['elf'])==sha(archive/old['elf'])
    a,b=old['after'],new['after']
    for record,root in [(a,archive),(b,ROOT)]:
        log=root/record['run']['log'];assert sha(log)==record['run']['log_sha256']
        values=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([0-9a-fA-F]{8})\]',log.read_text())]
        start=values.index(0x434d0001);assert values[start:start+12]==record['packet']
    assert a['instructions']==b['instructions'] and a['packet'][6:10]==b['packet'][6:10]
    assert b['cycles']<a['cycles']
    result['cases'].append({'iterations':n,'elf_sha256':new['elf_sha256'],
        'before_run':{**a['run'],'log':(archive/a['run']['log']).relative_to(ROOT).as_posix()},
        'instructions':b['instructions'],'before_cycles':a['cycles'],'after_cycles':b['cycles'],
        'before_ipc':a['ipc'],'after_ipc':b['ipc'],'cycles_saved':a['cycles']-b['cycles'],
        'speedup':a['cycles']/b['cycles'],'cycle_reduction_percent':100*(1-b['cycles']/a['cycles'])})
result['passed']=True
dump(ROOT/'out/performance/write_path/report.json',result)
for c in result['cases']:
    print(f"PASS write path Iter {c['iterations']}: {c['before_cycles']} -> {c['after_cycles']} cycles, "
          f"IPC {c['before_ipc']:.6f} -> {c['after_ipc']:.6f}",flush=True)

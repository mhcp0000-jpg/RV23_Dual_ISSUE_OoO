"""Run the preserved pre-change RTL against the exact current CoreMark ELF.

GCC's temporary STT_FILE names make full ELF hashes vary between identical
source builds. Preserve and reuse the actual ELF instead of assuming equality.
"""
from pathlib import Path
import json,re
from sim_runner import ROOT,Simulator,sha,dump

folder=ROOT/'out/performance/before'
old=json.loads((folder/'coremark_report.json').read_text())
current=json.loads((ROOT/'out/programs/report.json').read_text())
case=next(c for c in current['cases'] if c['name']=='coremark')
saved=folder/'shared_coremark.elf'
saved.write_bytes((ROOT/case['program']['elf']).read_bytes())
assert sha(saved)==case['program']['elf_sha256']
files=[]
for path,digest in old['model_inputs'].items():
    snapshot=folder/Path(path).name
    chosen=snapshot if snapshot.exists() else ROOT/path
    assert sha(chosen)==digest,'Baseline source differs: '+path
    files.append(chosen.relative_to(ROOT).as_posix())
with Simulator() as sim:
    model=sim.build('cache_perf_global_baseline','rv32_program_tb',files)
    dump(folder/'rechecked_model.json',model)
    run,text=sim.run([ROOT/model['binary'],f'+elf={saved.relative_to(ROOT).as_posix()}',
        '+trace_file=out/performance/before/rechecked_commit.csv',
        '+timeout_cycles=20000000','+expected_exit_code=0','+quiet_commit'],
        folder/'coremark_simulation.log',600)
    assert 'ELF AXI readback PASS' in text and 'PASS rv32_program_tb' in text
    values=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([0-9a-fA-F]{8})\]',text)]
    packet=values[values.index(0x434d0001):][:12]
    reference=next(c for c in old['cases'] if c['name']=='coremark')
    assert packet==reference['coremark']['packet'],'Baseline timing/CRC did not reproduce'
    assert sha(saved)==case['program']['elf_sha256']
    model.update(passed=True,run=run)
    dump(folder/'rechecked_model.json',model)
    result={'name':'coremark','passed':True,'program':case['program'],
        'run':run,'coremark':reference['coremark']}
    # Keep the canonical source keys for comparison with the current model.
    old.update(cases=[result],passed=True,state='finished',
        shared_elf=saved.relative_to(ROOT).as_posix(),shared_elf_sha256=sha(saved),
        rechecked_model='out/performance/before/rechecked_model.json')
    dump(folder/'coremark_report.json',old)
    print('PASS exact shared ELF baseline reproduced',packet[2],flush=True)

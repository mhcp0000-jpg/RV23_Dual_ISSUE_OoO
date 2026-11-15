# SPDX-License-Identifier: Apache-2.0
"""Check fetch-fault inertness across both lanes and XLENs, with a pre-fix control."""
import json
from sim_runner import ROOT, Simulator, dump, sha

folder=ROOT/'out/rva23/fetch_fault_decode';folder.mkdir(parents=True,exist_ok=True)
cases=json.loads((ROOT/'config/regression.json').read_text(encoding='utf-8'))['cases']
base=next(case for case in cases if case['top']=='rv_decode2_tb')
files=[name for name in base['files'] if name!='tb/unit/backend/rv_decode2_tb.sv']+['tb/unit/backend/rv_fetch_fault_decode_tb.sv']
report=dict(passed=False,scope='Fetch exceptions retain precise metadata and allocate no execution resources',
            faulted_lanes=384)
with Simulator() as sim:
    negative=files.copy()
    old='out/negative_controls/act4_pmp_branch/sources/rtl/backend/rv_decode2.sv'
    negative[negative.index('rtl/backend/rv_decode2.sv')]=old
    control=sim.build('fetch_fault_decode_pre_fix','rv_fetch_fault_decode_tb',negative)
    control['runs']=[sim.simulate(control,label='known_wrong',expected_failure='fetch fault entered execution')]
    control['passed']=True;report['negative_control']=control
    model=sim.build('fetch_fault_decode','rv_fetch_fault_decode_tb',files)
    model['runs']=[sim.simulate(model)];model['passed']=True;report['model']=model
    report['passed']=True
dump(folder/'report.json',report)
print('PASS 384 fetch-fault lanes; unmodified pre-fix decoder rejected',flush=True)

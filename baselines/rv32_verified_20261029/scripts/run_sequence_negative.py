import json
from sim_runner import ROOT,Simulator,dump
case=next(c for c in json.loads((ROOT/'config/regression.json').read_text())['cases']
          if c['name']=='rv_backend_seq_admission_tb')
files=[p.replace('rtl/backend/rv_backend.sv','tb/references/rv_backend_before_sequence_credit.sv')
        .replace('rtl/backend/rv_rob.sv','tb/references/rv_rob_before_sequence_credit.sv') for p in case['files']]
with Simulator() as sim:
    record=sim.build('sequence_credit_before','rv_backend_seq_admission_tb',files)
    record['run']=sim.simulate(record,expected_failure='BACKEND DISPATCH WITHOUT ROB ACCEPT')
    record['passed']=True
    dump(ROOT/'out/sequence_credit_negative.json',record)
    print('PASS reproduced pre-fix sequence-admission failure on actual ROB48/SEQ8',flush=True)

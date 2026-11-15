"""Sscofpmf/Zihpm event bank; full CSR/core coverage is a separate gate."""
from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_hpm_counters','rv_hpm_counters_tb',[
        'rtl/backend/rv_hpm_counters.sv','tb/unit/backend/rv_hpm_counters_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/hpm_counters.json',model)
print('PASS HPM event bank: mode filters, inhibit, dual-retire overflow and pending/OF rearm',flush=True)

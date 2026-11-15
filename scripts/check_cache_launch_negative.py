"""Prove the launch timing check rejects the preserved extra cache stages."""
from sim_runner import ROOT,Simulator,dump
files=['rtl/soc/rv_soc_pkg.sv','rtl/soc/rv23_pkg.sv','rtl/rv_ooo_pkg.sv',
       'rtl/soc/rv_local_mem_if.sv',
       'out/performance/wt_before/rtl/soc/rv23_cache.sv','tb/rv23_cache_fault_tb.sv']
with Simulator() as sim:
    model=sim.build('cache_launch_before','rv23_cache_fault_tb',files)
    model['run']=sim.simulate(model,expected_failure='Cache launch inserted an acceptance bubble')
    model['passed']=True
    dump(ROOT/'out/cache_launch_negative.json',model)
    print('PASS preserved cache stage rejected by acceptance-edge timing check',flush=True)

"""Exercise real cache + refill bridge, with stalled/error-injecting AXI target."""
import re
from sim_runner import ROOT, Simulator, dump
files=['rtl/rv_ooo_pkg.sv','rtl/soc/rv_soc_pkg.sv','rtl/soc/rv23_pkg.sv',
       'rtl/soc/rv_local_mem_if.sv','rtl/soc/rv_axi4_if.sv',
       'rtl/soc/rv23_cache.sv','rtl/soc/rv_local_to_axi_bridge.sv',
       'tb/rv23_cache_burst_tb.sv']
results=[]
with Simulator() as sim:
    for burst in [0,1]:
        model=sim.build(f'cache_burst_{burst}','rv23_cache_burst_tb',files,[f'-GBURST={burst}'])
        model['run']=sim.simulate(model)
        log=(ROOT/model['run']['log']).read_text()
        match=re.search(r'cold_cycles=(\d+) checks=(\d+)',log)
        assert match
        model.update(passed=True,cold_cycles=int(match[1]),checks=int(match[2]))
        results.append(model)
assert results[1]['cold_cycles'] < results[0]['cold_cycles']
dump(ROOT/'out/performance/cache_burst/unit.json',dict(passed=True,results=results,
    scope='Real cache/refill bridge with directed AXI target; not full SoC or physical timing sign-off'))
print('PASS cold refill cycles',results[0]['cold_cycles'],'->',results[1]['cold_cycles'],flush=True)
sram_results=[]
with Simulator() as sim:
    sram_files=files[:-1]+['rtl/soc/rv_axi_to_local_bridge.sv',
        'rtl/soc/rv_sram_1r1w.sv','rtl/soc/rv23_sram.sv','tb/rv23_cache_burst_sram_tb.sv']
    for burst in [0,1]:
        model=sim.build(f'cache_burst_sram_{burst}','rv23_cache_burst_sram_tb',sram_files,[f'-GBURST={burst}'])
        model['run']=sim.simulate(model)
        log=(ROOT/model['run']['log']).read_text()
        match=re.search(r'cold_cycles=(\d+) ar=(\d+) r=(\d+)',log);assert match
        model.update(passed=True,cold_cycles=int(match[1]),addresses=int(match[2]),beats=int(match[3]))
        sram_results.append(model)
assert sram_results[1]['cold_cycles']<sram_results[0]['cold_cycles']
dump(ROOT/'out/performance/cache_burst/sram.json',dict(passed=True,results=sram_results,
    scope='Real cache, both AXI bridges and synchronous SRAM; 32 cold lines then all 256 resident words and WT snoop. Excludes system arbiter and core.'))
print('PASS real SRAM 32 cold lines',sram_results[0]['cold_cycles'],'->',sram_results[1]['cold_cycles'],flush=True)

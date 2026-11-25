"""Request route locks, owner responses and transparent scalar hit timing."""
import json
from sim_runner import ROOT, Simulator, dump, sha

with Simulator() as sim:
    model=sim.build('head_cache_router','rv23_head_cache_router_tb',[
        'rtl/rv_ooo_pkg.sv','rtl/soc/rv_soc_pkg.sv','rtl/soc/rv23_pkg.sv',
        'rtl/soc/rv_local_mem_if.sv','rtl/soc/rv23_head_cache_router.sv','tb/rv23_head_cache_router_tb.sv'])
    run=sim.simulate(model)
log=(ROOT/run['log']).read_text()
assert 'PASS rv23_head_cache_router_tb cases=65 stream=20 span=19 latency=1' in log
dump(ROOT/'out/rva23/head_cache_router.json',dict(passed=True,
    scope='Routing component with one-cycle mock targets: stalls, route flips, response ownership, overlap and scalar II=1; real cache/SoC races have separate tests',
    model=model,run=run,driver_sha256=sha(__file__),cases=65,scalar_hit_latency=1,scalar_ii=1))
print('PASS shared-cache router 65 transactions; scalar hit II=1/latency=1; route and owner stalls')

"""Prove the same-line/different-word progress test detects the coarse lock."""
from sim_runner import ROOT,Simulator,dump
files=[p for p in (ROOT/'rtl/filelist.f').read_text().splitlines()
    if not p.startswith(('rtl/backend/','rtl/frontend/')) and p not in
    ['rtl/rv_ooo_core.sv','rtl/soc/rv23_core.sv','rtl/soc/rv23_soc_top.sv']]
files=[('out/performance/banked_stage1/rv23_cache.sv' if p=='rtl/soc/rv23_cache.sv' else p) for p in files]
files+=['tb/rv23_memory_tb.sv']
with Simulator() as sim:
    model=sim.build('cache_line_lock_before','rv23_memory_tb',files)
    model['run']=sim.simulate(model,expected_failure='Pending write blocked another word of the same line')
    model['passed']=True
    dump(ROOT/'out/cache_word_lock_negative.json',model)
    print('PASS coarse line lock independently rejected by progress test',flush=True)

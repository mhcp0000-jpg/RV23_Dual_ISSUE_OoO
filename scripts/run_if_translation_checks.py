"""IF translation preserves actual external response identity, including stale epochs."""
from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_if_translation','rv23_if_translate_tb',[
        'rtl/soc/rv23_page_walker.sv','rtl/soc/rv23_mmu.sv','rtl/soc/rv23_translation_port.sv',
        'rtl/soc/rv23_if_translate.sv','tb/rv23_if_translate_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/if_translation.json',model)
print('PASS IF translation external identity/stale epoch/fault ownership',flush=True)

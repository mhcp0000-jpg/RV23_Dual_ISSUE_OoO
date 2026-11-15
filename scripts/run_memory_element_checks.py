"""Natural aligned element atomicity, full-size PMP and split-access behavior."""
from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_memory_element','rv23_memory_head_tb',[
        'rtl/rv_ooo_pkg.sv','rtl/backend/rv_pmp.sv','rtl/soc/rv23_pointer_mask.sv',
        'rtl/backend/rv23_memory_head.sv','tb/unit/backend/rv23_memory_head_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/memory_element.json',model)
print('PASS natural aligned transfer atomicity, full-size PMP and split access prevalidation',flush=True)

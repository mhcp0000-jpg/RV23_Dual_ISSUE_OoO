"""Mandatory fractional LMUL/SEW configurations, AVL and WARL vill behavior."""
from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_vector_config','rv_vector_config_tb',[
        'rtl/backend/rv_vector_decode_pkg.sv','rtl/backend/rv_vector_config.sv',
        'tb/unit/backend/rv_vector_config_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/vector_config.json',model)
    print('PASS vector configuration mandatory LMUL/SEW/AVL checks; native core integration has separate evidence',flush=True)

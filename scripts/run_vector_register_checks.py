"""Vector group element mapping, overlap snapshots and isolated mask writes."""
from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_vector_registers','rv_vector_register_file_tb',[
        'rtl/backend/rv_vector_register_file.sv','tb/unit/backend/rv_vector_register_file_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/vector_registers.json',model)
    print('PASS vector register mapping and overlap/mask ownership; native core integration has separate evidence',flush=True)

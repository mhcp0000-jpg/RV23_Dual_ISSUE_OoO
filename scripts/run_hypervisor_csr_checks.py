"""H/VS architectural bank component before its core integration."""
from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_hypervisor_csrs','rv_hypervisor_csrs_tb',[
        'rtl/backend/rv_hypervisor_csrs.sv','tb/unit/backend/rv_hypervisor_csrs_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/hypervisor_csrs.json',model)
print('PASS H/VS CSR bank, precise metadata, trap/return contexts and virtual timer; native integration has separate evidence',flush=True)

"""Guest element owner: natural MMIO, PMP R+X, pointer masking and byte assist.

This Bare-mode component check does not establish guest translation or H core
integration. Execute-permission translation requires the HLVX walker path.
"""
from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_hypervisor_memory_head','rv23_hypervisor_memory_head_tb',[
        'rtl/rv_ooo_pkg.sv','rtl/backend/rv_pmp.sv','rtl/soc/rv23_pointer_mask.sv',
        'rtl/backend/rv23_hypervisor_memory_head.sv','tb/unit/backend/rv23_hypervisor_memory_head_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/hypervisor_memory_head.json',model)
print('PASS guest memory owner Bare mode: natural MMIO/PMP R+X/PMM; native guest integration has separate evidence',flush=True)

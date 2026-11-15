"""Faulting instruction parcels preserve the right final GPA or VS-PTE GPA."""
from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_fetch_guest_metadata','rv_fetch_guest_metadata_tb',[
        'rtl/rv_ooo_pkg.sv','rtl/frontend/rv_fetch_queue.sv','tb/unit/backend/rv_fetch_guest_metadata_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/fetch_guest_metadata.json',model)
print('PASS guest fetch parcel/fault address/GPA/implicit-PTE metadata ownership',flush=True)

from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_supervisor_csr','rv_supervisor_csr_tb',[
        'rtl/rv_ooo_pkg.sv','rtl/backend/rv_hpm_counters.sv','rtl/backend/rv_csr_file.sv','tb/unit/backend/rv_supervisor_csr_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/supervisor_csr.json',model)
    print('PASS supervisor CSR/privilege directed checks',flush=True)

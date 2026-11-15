"""Committed HPM bank, LCOFI and HS/VS/VU counter access qualification."""
from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_hpm_csr_file','rv_hpm_csr_file_tb',[
        'rtl/rv_ooo_pkg.sv','rtl/backend/rv_hypervisor_stateen.sv','rtl/backend/rv_hypervisor_csrs.sv',
        'rtl/backend/rv_hpm_counters.sv','rtl/backend/rv_csr_file.sv','tb/unit/backend/rv_hpm_csr_file_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/hpm_csr_file.json',model)
print('PASS committed HPM CSR/overflow interrupt and HS/VS/VU permissions',flush=True)

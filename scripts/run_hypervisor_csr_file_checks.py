"""Committed H/VS CSR-bank integration with the existing machine/HS CSR file."""
from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_hypervisor_csr_file','rv_hypervisor_csr_file_tb',[
        'rtl/rv_ooo_pkg.sv','rtl/backend/rv_hypervisor_stateen.sv','rtl/backend/rv_hypervisor_csrs.sv',
        'rtl/backend/rv_hpm_counters.sv','rtl/backend/rv_csr_file.sv','tb/unit/backend/rv_hypervisor_csr_file_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/hypervisor_csr_file.json',model)
print('PASS integrated H/VS CSR commit, interrupt priorities, trap metadata and returns; native core execution has separate evidence',flush=True)

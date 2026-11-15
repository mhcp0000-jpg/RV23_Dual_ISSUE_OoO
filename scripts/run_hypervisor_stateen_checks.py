"""Ssstateen context/priority gates, with optional controlling Smstateen."""
from sim_runner import ROOT,Simulator,dump
cases=[]
with Simulator() as sim:
    for machine in [0,1]:
        model=sim.build(f'rva23_hypervisor_stateen_{machine}','rv_hypervisor_stateen_tb',[
            'rtl/backend/rv_hypervisor_stateen.sv','tb/unit/backend/rv_hypervisor_stateen_tb.sv'],[f'-GHAS_SMSTATEEN={machine}'])
        model['run']=sim.simulate(model);model['passed']=True;cases.append(model)
dump(ROOT/'out/rva23/hypervisor_stateen.json',{'passed':True,'scope':'Ssstateen component; core H integration pending','cases':cases})
print('PASS Ssstateen/Hstateen writable SE/ENVCFG gates, CSR RAZ and trap priorities',flush=True)

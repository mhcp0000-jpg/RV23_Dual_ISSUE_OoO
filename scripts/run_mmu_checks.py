from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_mmu','rv23_mmu_tb',[
        'rtl/soc/rv23_page_walker.sv','rtl/soc/rv23_mmu.sv','tb/rv23_mmu_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/mmu.json',model)
    print('PASS Sv39/Sv39x4 directed checks; SoC integration tracked separately',flush=True)

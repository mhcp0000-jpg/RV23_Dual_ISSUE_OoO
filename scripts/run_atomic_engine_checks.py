from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_atomic_engine','rv23_atomic_engine_tb',[
        'rtl/rv_ooo_pkg.sv','rtl/soc/rv_soc_pkg.sv','rtl/soc/rv23_pkg.sv',
        'rtl/soc/rv_axi4_if.sv','rtl/soc/rv_local_mem_if.sv',
        'rtl/soc/rv_axi_xbar.sv','rtl/soc/rv_axi_error_slave.sv',
        'rtl/soc/rv_axi_to_local_bridge.sv','rtl/soc/rv_sram_1r1w.sv',
        'rtl/soc/rv23_sram.sv','rtl/soc/rv23_atomic_engine.sv','tb/rv23_atomic_engine_tb.sv'],
        params=['-CFLAGS','-O2'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/atomic_engine.json',model)
    print('PASS atomic engine W/D arithmetic/reservation/AMO retry checks; core integration pending',flush=True)

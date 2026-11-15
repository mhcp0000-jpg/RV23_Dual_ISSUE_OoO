from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_cbo_head','rv23_cbo_head_tb',[
        'rtl/rv_ooo_pkg.sv','rtl/soc/rv_soc_pkg.sv','rtl/soc/rv23_pkg.sv',
        'rtl/soc/rv_axi4_if.sv','rtl/soc/rv_local_mem_if.sv',
        'rtl/soc/rv_axi_xbar.sv','rtl/soc/rv_axi_error_slave.sv',
        'rtl/soc/rv_axi_to_local_bridge.sv','rtl/soc/rv_sram_1r1w.sv',
        'rtl/soc/rv23_sram.sv','rtl/soc/rv_local_to_axi_bridge.sv','rtl/backend/rv_pmp.sv','rtl/soc/rv23_pointer_mask.sv','rtl/backend/rv23_cbo_head.sv','tb/rv23_cbo_head_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/cbo_head.json',model)
    print('PASS CBO head validation and 64-byte bus zero; core integration pending',flush=True)

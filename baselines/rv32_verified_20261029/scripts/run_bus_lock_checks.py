from sim_runner import ROOT,Simulator,dump
files=['rtl/soc/rv_soc_pkg.sv','rtl/soc/rv23_pkg.sv','rtl/soc/rv_axi4_if.sv',
       'rtl/soc/rv_axi_xbar.sv','tb/rv_axi_xbar_stall_tb.sv']
report={'passed':False,'scope':'Stalled AXI AR/AW address ownership plus pre-fix negative control','cases':[]}
path=ROOT/'out/bus_lock_report.json'
with Simulator() as sim:
    for negative in [False,True]:
        selected=list(files)
        if negative:selected[3]='tb/references/rv_axi_xbar_before_stall_lock.sv'
        record=sim.build('xbar_lock_'+('before' if negative else 'fixed'),'rv_axi_xbar_stall_tb',selected)
        record['run']=sim.simulate(record,expected_failure=
            'AR ownership changed under backpressure' if negative else None)
        record['passed']=True
        report['cases'].append(record);dump(path,report)
        print('PASS',record['name'],flush=True)
report['passed']=True;dump(path,report)

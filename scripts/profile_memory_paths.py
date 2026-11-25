"""Measure actual CPU/IF accept-to-first-response latency on the system TB."""
import argparse
from sim_runner import ROOT,Simulator,dump
ap=argparse.ArgumentParser();ap.add_argument('--label',required=True)
ap.add_argument('--source-root',default='.',help='Preserved source tree relative to this project')
args=ap.parse_args();source_root=(ROOT/args.source_root).resolve()
source_root.relative_to(ROOT)
name='memory_latency_'+args.label
folder=ROOT/'out/performance'/name;folder.mkdir(parents=True,exist_ok=True)
source=(source_root/'tb/rv23_memory_tb.sv').read_text().replace('module rv23_memory_tb;',f'module {name};')
monitor='''
  time probe_accept[0:2],probe_if_accept;
  bit [2:0] probe_pending=0;
  bit probe_if_pending=0;
  logic [2:0][31:0] probe_addr;
  logic [2:0] probe_write;
  always @(posedge clk_i) if(rst_ni) begin
    for(int p=0;p<3;p++) if(req_valid[p] && req_ready[p]) begin
      probe_accept[p]=$time;probe_pending[p]=1;
      probe_addr[p]=req_addr[p];probe_write[p]=req_write[p];
      $display("MEM_ACCEPT port=%0d addr=%h write=%b t=%0t",p,req_addr[p],req_write[p],$time);
    end
    if(if_valid && if_ready) begin probe_if_accept=$time;probe_if_pending=1;end
  end
  always @(negedge clk_i) if(rst_ni) begin
    for(int p=0;p<3;p++) if(probe_pending[p] && rsp_valid[p]) begin
      $display("MEM_LAT port=%0d addr=%h write=%b cycles=%0d",p,probe_addr[p],probe_write[p],1+int'(($time-probe_accept[p])/10));
      probe_pending[p]=0;
    end
    if(probe_if_pending && if_rsp_valid) begin
      $display("IF_LAT addr=%h cycles=%0d",if_addr,1+int'(($time-probe_if_accept)/10));
      probe_if_pending=0;
    end
  end
'''
source=source.replace('  initial begin #2000000;',monitor+'\n  initial begin #2000000;')
needle='    // Byte lane write-through and invalidation of both caches.'
assert needle in source
source=source.replace(needle,'''    $display("DUAL_HIT_PROBE_BEGIN");
    fork
      access_mem(0,0,32'h80000000,0,0,3,0,v0);
      access_mem(1,0,32'h80000008,0,0,3,0,v1);
    join
    if(v0!==64'h100 || v1!==64'h101) $fatal(1,"Dual hit data");
    $display("DUAL_HIT_PROBE_END");
'''+needle)
path=folder/(name+'.sv');path.write_text(source)
files=[p for p in (ROOT/'rtl/filelist.f').read_text().splitlines()
    if not p.startswith(('rtl/backend/','rtl/frontend/')) and p not in
    ['rtl/rv_ooo_core.sv','rtl/soc/rv23_core.sv','rtl/soc/rv23_soc_top.sv']]
files=[(source_root/p).relative_to(ROOT).as_posix() for p in files]+[path.relative_to(ROOT).as_posix()]
with Simulator() as sim:
    model=sim.build(name,name,files)
    run,text=sim.run([ROOT/model['binary']],folder/'simulation.log',120)
    assert 'PASS rv23_memory_tb' in text
    model.update(passed=True,run=run)
    dump(folder/'report.json',model)
    print('\n'.join(x for x in text.splitlines() if 'LAT ' in x or 'PROBE' in x),flush=True)

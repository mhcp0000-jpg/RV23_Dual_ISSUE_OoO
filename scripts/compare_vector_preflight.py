"""Same functional stream, current aligned preflight versus byte-preflight control."""
import re
from sim_runner import ROOT, Simulator, dump, sha

folder=ROOT/'out/performance/vector_preflight';folder.mkdir(parents=True,exist_ok=True)
path=ROOT/'rtl/backend/rv23_hypervisor_memory_head.sv'
source=path.read_text(encoding='utf-8')
anchor='index_q==last_byte || (natural_q && index_q==0 && full_pmp_allow)'
assert source.count(anchor)==1
control=folder/'byte_preflight_control.sv'
control.write_text(source.replace(anchor,'index_q==last_byte'),encoding='utf-8')
files=['rtl/rv_ooo_pkg.sv','rtl/backend/rv_pmp.sv','rtl/soc/rv23_pointer_mask.sv',
       path.relative_to(ROOT).as_posix(),'tb/unit/backend/rv23_hypervisor_memory_head_tb.sv',
       'tb/rv23_memory_preflight_perf_tb.sv']
results={}
with Simulator() as sim:
    for label in ['byte_control','aligned']:
        inputs=[control.relative_to(ROOT).as_posix() if p==files[3] and label=='byte_control' else p for p in files]
        model=sim.build('vector_preflight_'+label,'rv23_memory_preflight_perf_tb',inputs)
        run=sim.simulate(model)
        log=(ROOT/run['log']).read_text(encoding='utf-8')
        m=re.search(r'PREFLIGHT_PERF cycles=(\d+) checks=(\d+) aligned_checks=(\d+) requests=(\d+)',log)
        assert m
        results[label]=dict(model=model,run=run,**dict(zip(['cycles','checks','aligned_checks','requests'],map(int,m.groups()))))
        print(label,{k:results[label][k] for k in ['cycles','checks','aligned_checks','requests']},flush=True)
a,b=results['byte_control'],results['aligned']
assert b['requests']==a['requests'] and b['aligned_checks']<a['aligned_checks'] and b['cycles']<a['cycles']
dump(folder/'report.json',dict(passed=True,scope='Bare-mode memory-owner mixed functional stream with identical backpressure; not CoreMark or physical timing',
    driver_sha256=sha(__file__),production_sha256=sha(path),control_sha256=sha(control),results=results,
    cycles_saved=a['cycles']-b['cycles']))
print('PASS aligned preflight reduces work without changing physical transaction count',flush=True)

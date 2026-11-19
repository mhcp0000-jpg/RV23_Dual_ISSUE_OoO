"""Inject a secret-dependent VCLZ early exit; paired timing must reject it."""
import json
from sim_runner import ROOT,Simulator,sha,dump
folder=ROOT/'out/negative_controls/vector_timing';folder.mkdir(parents=True,exist_ok=True)
positive=json.loads((ROOT/'out/rva23/vector_timing/report.json').read_text())
assert positive['passed']
for p,h in positive['model']['inputs'].items():assert sha(ROOT/p)==h,p
vectors=ROOT/'out/rva23/vector_timing/vectors.hex'
assert sha(vectors)==positive['vector_sha256']
original=ROOT/'rtl/backend/rv_vector_engine.sv';text=original.read_text(encoding='utf-8')
anchor='if(index_q>=effective_length)begin'
assert text.count(anchor)==1
mutant=folder/'rv_vector_engine.sv'
mutant.write_text(text.replace(anchor,
    'if(operation==VI_VCLZ && read_data[0]==0)state_q<=FINISH;\n          else '+anchor),encoding='utf-8')
files=[mutant.relative_to(ROOT).as_posix() if p=='rtl/backend/rv_vector_engine.sv' else p
       for p in (ROOT/'rtl/filelist.f').read_text().splitlines()]+['tb/unit/backend/rv_vector_timing_tb.sv']
with Simulator() as sim:
    model=sim.build('rva23_vector_timing_negative','rv_vector_timing_tb',files)
    model['run']=sim.simulate(model,[f'+vectors={vectors.relative_to(ROOT).as_posix()}',
        f'+latencies={(folder/"latencies.csv").relative_to(ROOT).as_posix()}'],
        expected_failure='different timing/legality',timeout=120)
    model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'Expected failure control: data-dependent VCLZ early exit rejected by the same paired timing testbench and vectors',
        'model':model,'original_sha256':sha(original),'mutant_sha256':sha(mutant),'vector_sha256':sha(vectors),
        'positive_report_sha256':sha(ROOT/'out/rva23/vector_timing/report.json'),'generator_sha256':sha(__file__)})
print('PASS timing negative control: secret-dependent VCLZ early exit was rejected',flush=True)

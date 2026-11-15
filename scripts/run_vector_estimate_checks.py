"""RTL estimates versus original Spike helper execution and normative table data."""
import json,random
from sim_runner import ROOT,Simulator,DEV,sha,dump
folder=ROOT/'out/rva23/vector_estimates';folder.mkdir(parents=True,exist_ok=True)
table=ROOT/'config/vector_estimates/tables.json';provenance=json.loads(table.read_text())
for source in provenance['sources']:
    if 'file' in source:assert sha(ROOT/source['file'])==source['sha256']
    if 'selected_reference_file' in source:assert sha(ROOT/source['selected_reference_file'])==source['selected_reference_sha256']
path=folder/'inputs.txt';count=0;rng=random.Random(230007)
with path.open('w') as stream:
    def append(width,value):
        global count
        for sqrt in [0,1]:
            for rm in range(5):stream.write(f'{width} {sqrt} {rm} {value:016x}\n');count+=1
    for value in range(65536):append(16,value)
    for width,eb,fb in [(32,8,23),(64,11,52)]:
        maxexp=(1<<eb)-1;bias=(1<<(eb-1))-1;sign=1<<(width-1)
        values={0,sign,maxexp<<fb,(maxexp<<fb)|sign}
        for exp in [0,1,2,bias-1,bias,bias+1,maxexp-2,maxexp-1,maxexp]:
            for index in range(128):
                for low in [0,(1<<(fb-7))-1]:
                    for prefix in [0,sign]:values.add(prefix|(exp<<fb)|(index<<(fb-7))|low)
        for bit in range(fb):
            for prefix in [0,sign]:values.update([prefix|(1<<bit),prefix|((1<<(bit+1))-1)])
        values.update(rng.getrandbits(width) for _ in range(5000))
        for value in sorted(values):append(width,value)
with Simulator() as sim:
    oracle=folder/'reference.exe'
    compile_oracle,_=sim.run([DEV/'gcc.exe','-O2','-std=c11',sim.drive+'/tb/oracles/vector_estimate_reference.c',
        '-o',sim.drive+'/'+oracle.relative_to(ROOT).as_posix()],folder/'oracle_compile.log',60)
    vector=folder/'vectors.txt'
    reference,text=sim.run([oracle,path.relative_to(ROOT).as_posix(),vector.relative_to(ROOT).as_posix()],folder/'reference.log',60)
    assert f'vectors={count}' in text
    model=sim.build('rva23_vector_estimates','rv_vector_fp_estimate_tb',[
        'rtl/backend/rv_vector_estimate_tables_pkg.sv','rtl/backend/rv_vector_fp_estimate.sv',
        'tb/unit/backend/rv_vector_fp_estimate_tb.sv'])
    model['run']=sim.simulate(model,[f'+vectors={vector.relative_to(ROOT).as_posix()}']);model['passed']=True
    dump(folder/'report.json',{'passed':True,'scope':'Exact estimate component, FP16 exhaustive plus FP32/64 boundaries/random; vector FP/native core integration has separate evidence',
        'vectors':count,'input_sha256':sha(path),'vectors_sha256':sha(vector),'table_sha256':sha(table),
        'generator_sha256':sha(__file__),'table_generator_sha256':sha(ROOT/'scripts/gen_vector_estimate_tables.py'),
        'oracle_inputs':{p:sha(ROOT/p) for p in ['tb/oracles/vector_estimate_reference.c','tb/oracles/vector_estimate_helpers.c']},
        'oracle_binary_sha256':sha(oracle),'oracle_compile':compile_oracle,'reference':reference,'model':model})
    print('PASS vector estimates versus Spike exact vectors',count,flush=True)

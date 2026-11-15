"""Content-bound native vector evidence, distinct from full RVA23 sign-off."""
import json
from sim_runner import ROOT,sha,dump
def fresh(inputs):
    for p,h in inputs.items():assert sha(ROOT/p)==h,p
report=json.loads((ROOT/'out/rva23/vector_integration/report.json').read_text())
assert report['passed'];model=report['model'];fresh(model['inputs']);fresh(report['runtime_inputs'])
assert sha(ROOT/model['binary'])==model['binary_sha256']
assert sha(ROOT/'scripts/run_vector_integration.py')==report['generator_sha256']
assert sha(ROOT/'out/rva23/vector_integration/vector.ld')==report['linker_sha256']
for step in ['compile','build']:
    r=model[step];assert r['passed'];assert sha(ROOT/r['log'])==r['log_sha256']
assert {c['name'] for c in report['cases']}=={'vector_integer_engine','vector_fp_engine','vector_memory_engine'}
for case in report['cases']:
    assert case['passed'];name=case['name'];folder=ROOT/'out/rva23/vector_integration'
    for path,key in [(folder/(name+'.S'),'source_sha256'),(folder/(name+'.elf'),'elf_sha256'),
                     (folder/(name+'_commit.csv'),'trace_sha256'),(ROOT/f'out/rva23/{name}/program.hex','packet_sha256')]:
        assert sha(path)==case[key],path
    r=case['run'];assert r['passed'];assert sha(ROOT/r['log'])==r['log_sha256']
    log=(ROOT/r['log']).read_text();assert 'PASS rv32_program_tb' in log and 'data=0x56454331' in log
for name in ['vector_state','vector_sv39']:
    r=json.loads((ROOT/f'out/rva23/{name}/report.json').read_text());assert r['passed'];fresh(r['model_inputs'])
    assert r['binary_sha256']==model['binary_sha256']
    assert sha(ROOT/f'scripts/run_{name}_integration.py')==r['generator_sha256']
    if isinstance(r['source_sha256'],dict):fresh(r['source_sha256'])
    else:assert sha(ROOT/'sw/tests/rv64_vector_state.S')==r['source_sha256']
    assert sha(ROOT/f'out/rva23/{name}/test.elf')==r['elf_sha256']
    assert sha(ROOT/f'out/rva23/{name}/commit.csv')==r['trace_sha256']
    run=r['run'];assert run['passed'];assert sha(ROOT/run['log'])==run['log_sha256']
    assert 'PASS rv32_program_tb' in (ROOT/run['log']).read_text()
output={'passed':True,'scope':'Native vector integration evidence on the H-enabled SoC; H/Sha and timing evidence have separate audits; complete architectural validation remains separate',
    'packets':{c['name']:c['packets'] for c in report['cases']},'model_inputs':model['inputs'],
    'binary_sha256':model['binary_sha256'],'reports':{p:sha(ROOT/p) for p in [
        'out/rva23/vector_integration/report.json','out/rva23/vector_state/report.json','out/rva23/vector_sv39/report.json']}}
dump(ROOT/'out/rva23/vector_architectural_evidence.json',output)
print('PASS fresh full-core V evidence; complete RVA23 architectural validation remains separate')

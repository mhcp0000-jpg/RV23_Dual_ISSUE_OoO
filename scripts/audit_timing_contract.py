"""Bind directed scalar/vector timing evidence and the rejecting mutation."""
import csv,json
from sim_runner import ROOT,sha,dump

def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
def fresh(inputs):
    for p,h in inputs.items():assert sha(ROOT/p)==h,p
def run(record,negative=False):
    assert record['passed'] and (record['exit_code']!=0 if negative else record['exit_code']==0)
    assert sha(ROOT/record['log'])==record['log_sha256'],record['log']
def model(record):
    fresh(record['inputs']);assert sha(ROOT/record['binary'])==record['binary_sha256']
    run(record['compile']);run(record['build'])

scalar=read('out/rva23/scalar_timing/report.json');assert scalar['passed'];model(scalar['model']);fresh(scalar['runtime_inputs'])
assert sha(ROOT/'scripts/run_scalar_timing_integration.py')==scalar['generator_sha256']
assert sha(ROOT/'out/rva23/scalar_timing/test.S')==scalar['source_sha256']
assert scalar['fixtures']==len(scalar['runs'])==16 and scalar['measured_instructions']==408
assert scalar['instructions_with_varied_results']>100
for case in scalar['runs']:
    run(case['compile']);run(case['run'])
    assert sha(ROOT/case['elf'])==case['elf_sha256'];assert sha(ROOT/case['trace'])==case['trace_sha256']

vector=read('out/rva23/vector_timing/report.json');assert vector['passed'];model(vector['model']);run(vector['model']['run'])
folder=ROOT/'out/rva23/vector_timing'
assert sha(ROOT/'scripts/run_vector_timing_checks.py')==vector['generator_sha256']
for path,key in [(folder/'instructions.S','source_sha256'),(folder/'vectors.hex','vector_sha256'),(folder/'latencies.csv','latencies_sha256')]:
    assert sha(path)==vector[key],path
with (folder/'latencies.csv').open(newline='') as stream:rows=list(csv.DictReader(stream))
assert len(rows)==vector['paired_probes']==84348
assert len({r['group'] for r in rows if r['illegal']=='0'})==vector['forms']==231

negative=read('out/negative_controls/vector_timing/report.json');assert negative['passed'];model(negative['model']);run(negative['model']['run'],True)
assert negative['model']['run']['expected_failure']=='different timing/legality'
assert sha(ROOT/'rtl/backend/rv_vector_engine.sv')==negative['original_sha256']
assert sha(ROOT/'out/negative_controls/vector_timing/rv_vector_engine.sv')==negative['mutant_sha256']
assert negative['vector_sha256']==vector['vector_sha256']
assert sha(folder/'report.json')==negative['positive_report_sha256']
assert sha(ROOT/'scripts/run_vector_timing_negative.py')==negative['generator_sha256']
dump(ROOT/'out/rva23/timing_contract_evidence.json',{'passed':True,
    'scope':'Finite current Zkt/Zvkt-directed evidence plus rejecting secret-dependent-latency mutation. Not formal noninterference, complete architecture, synthesis or system-wide security sign-off.',
    'scalar_fixtures':16,'scalar_instructions_per_trace':408,'vector_forms':231,'paired_vector_probes':84348,
    'reports':{p:sha(ROOT/p) for p in ['out/rva23/scalar_timing/report.json','out/rva23/vector_timing/report.json','out/negative_controls/vector_timing/report.json']},
    'audit_sha256':sha(__file__)})
print('PASS bound scalar/vector timing evidence and rejecting early-exit mutation',flush=True)

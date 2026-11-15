"""Audit fresh development evidence without implying architectural V support."""
import json
from sim_runner import ROOT,sha,dump

def fresh(inputs):
    for path,digest in inputs.items():assert sha(ROOT/path)==digest,path
def model(record):
    assert record['passed'];fresh(record['inputs'])
    assert sha(ROOT/record['binary'])==record['binary_sha256']
    for name in ['compile','build','run']:
        r=record[name];assert r['passed']
        assert sha(ROOT/r['log'])==r['log_sha256'],r['log']
    assert record['run']['witnesses']

decode=json.loads((ROOT/'out/rva23/vector_decode/report.json').read_text());assert decode['passed']
model(decode['model'])
assert sha(ROOT/'scripts/run_vector_decode_checks.py')==decode['generator_sha256']
assert sha(ROOT/'config/vector_opcode_tables/encodings.json')==decode['opcode_table_sha256']
assert sha(ROOT/'out/rva23/vector_decode/vectors.hex')==decode['vectors_sha256']
integer=json.loads((ROOT/'out/rva23/vector_integer/report.json').read_text());assert integer['passed']
assert sha(ROOT/'scripts/vector_integer_reference.py')==integer['oracle_sha256']
assert sha(ROOT/'scripts/run_vector_integer_checks.py')==integer['generator_sha256']
for case in integer['cases']:
    model(case['model'])
    assert sha(ROOT/f'out/rva23/vector_integer/w{case["width"]}.hex')==case['vector_sha256']
for name in ['vector_config','vector_registers']:
    model(json.loads((ROOT/f'out/rva23/{name}.json').read_text()))
engine=json.loads((ROOT/'out/rva23/vector_integer_engine/report.json').read_text())
assert engine['passed'];model(engine['model'])
assert sha(ROOT/'scripts/run_vector_integer_engine_checks.py')==engine['generator_sha256']
assert sha(ROOT/'scripts/vector_integer_reference.py')==engine['oracle_sha256']
assert sha(ROOT/'out/rva23/vector_integer_engine/program.hex')==engine['vectors_sha256']
extra={}
for name,vector in [('vector_estimates','vectors.txt'),('vector_fp_integer','vectors.hex'),
                    ('vector_fp_lane','vectors.hex'),('vector_fp_engine','program.hex'),
                    ('vector_memory_engine','program.hex')]:
    record=json.loads((ROOT/f'out/rva23/{name}/report.json').read_text())
    assert record['passed'];model(record['model'])
    script_name='vector_estimate' if name=='vector_estimates' else name
    assert sha(ROOT/f'scripts/run_{script_name}_checks.py')==record['generator_sha256']
    assert sha(ROOT/f'out/rva23/{name}/{vector}')==record.get('vector_sha256',record.get('vectors_sha256'))
    if 'oracle_inputs' in record:fresh(record['oracle_inputs'])
    if 'oracle_sha256' in record:assert sha(ROOT/'scripts/fp_reference.py')==record['oracle_sha256']
    extra[name]=record
estimate=extra['vector_estimates']
assert sha(ROOT/'out/rva23/vector_estimates/reference.exe')==estimate['oracle_binary_sha256']
for name in ['oracle_compile','reference']:
    record=estimate[name];assert record['passed'];assert sha(ROOT/record['log'])==record['log_sha256']
assert sha(ROOT/'scripts/gen_vector_estimate_tables.py')==estimate['table_generator_sha256']
table=json.loads((ROOT/'config/vector_opcode_tables/encodings.json').read_text())
assert sha(ROOT/'scripts/gen_vector_decode.py')==table['generator_sha256']
for source in table['sources']:assert sha(ROOT/source['file'])==source['sha256']
report={'passed':True,'scope':'Standalone vector components; architectural integration and profile validation have separate audits',
    'encoding_forms':decode['forms'],'gnu_vectors':decode['gnu_vectors'],
    'integer_math_cases':sum(x['math_cases'] for x in integer['cases']),
    'integer_owner_instruction_packets':engine['instructions'],
    'fp_estimate_exact_cases':extra['vector_estimates']['vectors'],
    'fp_integer_exact_cases':extra['vector_fp_integer']['vectors'],
    'fp_lane_cases':extra['vector_fp_lane']['vectors'],
    'fp_owner_instruction_packets':extra['vector_fp_engine']['instructions'],
    'memory_owner_packets':extra['vector_memory_engine']['packets'],
    'unsupported_operation_checks':sum(x['unsupported_classes'] for x in integer['cases']),
    'reports':{p:sha(ROOT/p) for p in ['out/rva23/vector_decode/report.json','out/rva23/vector_integer/report.json',
        'out/rva23/vector_config.json','out/rva23/vector_registers.json','out/rva23/vector_integer_engine/report.json']+
        [f'out/rva23/{name}/report.json' for name in extra]}}
dump(ROOT/'out/rva23/vector_components.json',report)
print('PASS fresh vector component evidence:',report['integer_math_cases'],'math cases; native integration has a separate audit')

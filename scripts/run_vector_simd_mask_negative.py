"""Reproduce the masked packed-write bug in an isolated RTL copy."""
import json
from sim_runner import ROOT, Simulator, dump, sha, source_inputs

folder=ROOT/'out/negative_controls/vector_simd_mask';folder.mkdir(parents=True,exist_ok=True)
prior_path=ROOT/'out/rva23/vector_integer_engine/report.json'
prior=json.loads(prior_path.read_bytes());assert prior['passed']
assert prior['model']['inputs']==source_inputs(prior['model']['inputs'])
original=ROOT/'rtl/backend/rv_vector_register_file.sv'
text=original.read_text();anchor='write_data=(write_packed_data_i & write_bit_mask_i)<<(write_offset%128);'
assert text.count(anchor)==1
mutant=folder/'rv_vector_register_file.sv'
mutant.write_text(text.replace(anchor,'write_data=write_packed_data_i<<(write_offset%128);'))
files=[mutant.relative_to(ROOT).as_posix() if p=='rtl/backend/rv_vector_register_file.sv' else p
    for p in prior['model']['inputs'] if p.endswith(('.sv','.v'))]
vectors=ROOT/'out/rva23/vector_integer_engine/program.hex'
assert sha(vectors)==prior['vectors_sha256']
with Simulator() as sim:
    model=sim.build('vector_simd_mask_negative','rv_vector_integer_engine_tb',files)
    run=sim.simulate(model,[f'+vectors={vectors.relative_to(ROOT).as_posix()}'],expected_failure='vector owner case138')
dump(folder/'report.json',dict(passed=True,scope='Expected-failure control: masked-off SIMD values corrupt old destination in isolated RTL copy',
    model=model,run=run,original_sha256=sha(original),mutant_sha256=sha(mutant),vectors_sha256=sha(vectors),
    positive_report_sha256=sha(prior_path),driver_sha256=sha(__file__)))
print('PASS expected failure: unmasked packed write data rejected at masked-add case138')

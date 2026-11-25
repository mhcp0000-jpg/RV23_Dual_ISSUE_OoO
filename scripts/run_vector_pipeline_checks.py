"""Observe II=1 vector arithmetic and drained completion on the value corpus."""
import json
import re
from sim_runner import ROOT, Simulator, dump, sha, source_inputs

prior=json.loads((ROOT/'out/rva23/vector_integer_engine/report.json').read_bytes())
assert prior['passed'] and prior['generator_sha256']==sha(ROOT/'scripts/run_vector_integer_engine_checks.py')
assert prior['model']['inputs']==source_inputs(prior['model']['inputs'])
vectors=ROOT/'out/rva23/vector_integer_engine/program.hex'
assert sha(vectors)==prior['vectors_sha256']
files=(ROOT/'rtl/filelist.f').read_text().splitlines()+[
    'tb/unit/backend/rv_vector_integer_engine_tb.sv','tb/rv_vector_pipeline_tb.sv']
with Simulator() as sim:
    model=sim.build('vector_pipeline','rv_vector_pipeline_tb',files)
    run=sim.simulate(model,[f'+vectors={vectors.relative_to(ROOT).as_posix()}'])
log=(ROOT/run['log']).read_text()
m=re.search(r'VECTOR_PIPELINE issues=(\d+) writes=(\d+) max_add=(\d+) max_write=(\d+)',log)
assert m
issues,writes,max_add,max_write=map(int,m.groups())
assert issues>=64 and max_add>=8 and max_write>=8
packed=re.search(r'VECTOR_SIMD parallel=16/8/4/2 batches=(\d+)/(\d+)/(\d+)/(\d+) full_writes=(\d+)',log)
assert packed and all(int(value)>=8 for value in packed.groups())
assert f'instruction packets={prior["instructions"]}' in log
extension=re.search(r'VECTOR_EXT issues=(\d+) max_run=(\d+) parallel=(\d+)',log)
assert extension and int(extension[2])>=8 and int(extension[3])>=8
dump(ROOT/'out/rva23/vector_pipeline.json',dict(passed=True,scope='Component arithmetic stream and consecutive pipeline/complete-drain witnesses; not physical timing or native-core sign-off',
    model=model,run=run,prior_report_sha256=sha(ROOT/'out/rva23/vector_integer_engine/report.json'),vectors_sha256=sha(vectors),
    driver_sha256=sha(__file__),issues=issues,writes=writes,max_add=max_add,max_write=max_write,
    parallel_elements=[16,8,4,2],packed_batch_runs=list(map(int,packed.groups())),
    extension=dict(zip(['issues','max_run','parallel'],map(int,extension.groups())))))
print('PASS 128-bit vector II=1, SEW8/16/32/64 parallelism 16/8/4/2, drained completion',issues,writes,max_add,max_write)

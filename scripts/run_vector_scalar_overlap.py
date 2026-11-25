"""Native scalar/vector overlap, precise recovery and FP co-retirement witnesses."""
import csv,json,re
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare,read_csv
from sim_runner import ROOT,Simulator,dump,sha,source_inputs

folder=ROOT/'out/rva23/vector_scalar_overlap'
source=ROOT/'sw/tests/rv64_vector_scalar_overlap.S'
def verify(reference,rtl):
    rows=read_csv(rtl)
    events,mismatch=compare(read_csv(reference),rows)
    assert mismatch is None,mismatch
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert len(traps)==1 and int(traps[0]['cause'])==2,traps
    return dict(matched_events=events,illegal_vector_traps=1)

outcomes=run_fixture(source,folder,__file__,verify)
report=json.loads((folder/'report.json').read_bytes())
report['passed']=False;dump(folder/'report.json',report)
files=(ROOT/'rtl/filelist.f').read_text().splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/rv32_program_tb.sv','tb/rv23_vector_scalar_overlap_tb.sv','tb/e2e/dpi/elf_loader.cpp']
with Simulator() as sim:
    model_path=folder/'pipeline_model.json'
    model=json.loads(model_path.read_bytes()) if model_path.exists() else None
    if not model or model['inputs']!=source_inputs(files) or sha(ROOT/model['binary'])!=model['binary_sha256']:
        model=sim.build('rv23_vector_scalar_overlap','rv23_vector_scalar_overlap_tb',files)
        dump(model_path,model)
    trace=folder/'observed.csv'
    run,log=sim.run([ROOT/model['binary'],f'+elf={(folder/"test.elf").relative_to(ROOT).as_posix()}',
        f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit','+htif',
        '+timeout_cycles=100000','+expected_exit_code=0'],folder/'observed.log',120)
assert model['inputs']==source_inputs(model['inputs'])
assert verify(folder/'sail.csv',trace)==outcomes
m=re.search(r'VECTOR_SCALAR_OVERLAP int=(\d+) fp=(\d+) fp_coretire=(\d+) busy_start=(\d+) branch_keep=(\d+)',log)
assert m and all(int(n)>0 for n in m.groups())
report.update(passed=True,pipeline_model=model,pipeline_run=run,
    pipeline_trace_sha256=sha(trace),pipeline=dict(zip(['int','fp','fp_coretire','busy_start','branch_keep'],map(int,m.groups()))))
dump(folder/'report.json',report)
print('PASS native scalar/vector overlap, FP co-retire, pending MMIO and precise recovery',outcomes,report['pipeline'],flush=True)

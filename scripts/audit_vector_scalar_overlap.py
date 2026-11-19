"""Audit current-source native overlap, precise IRQ and the real RTL negative control."""
import json,re,subprocess
from collections import defaultdict
from run_sail_event_comparison import compare,read_csv
from sim_runner import ROOT,GCC,dump,sha,source_inputs

def step(record,negative=False):
    assert record['passed'] and (record['exit_code']!=0 if negative else record['exit_code']==0)
    assert sha(ROOT/record['log'])==record['log_sha256']
    return (ROOT/record['log']).read_text(encoding='utf-8')

def model(record):
    assert record['inputs']==source_inputs(record['inputs'])
    assert sha(ROOT/record['binary'])==record['binary_sha256']
    for phase in ['compile','build']:step(record[phase])

def load(path):
    record=json.loads((ROOT/path).read_bytes());assert record['passed']
    return record

def main():
    paths=['out/rva23/vector_scalar_overlap/report.json',
           'out/rva23/vector_scalar_irq/report.json',
           'out/negative_controls/vector_system_wake/report.json']
    positive,irq,negative=map(load,paths)
    assert positive['generator_sha256']==sha(ROOT/'scripts/run_vector_scalar_overlap.py')
    assert positive['runtime_inputs']==source_inputs(positive['runtime_inputs'])
    assert positive['source_sha256']==sha(ROOT/'sw/tests/rv64_vector_scalar_overlap.S')
    assert positive['model']['top']=='rv32_program_tb'
    assert {'-GXLEN=64','-GHAS_H=1','-GHAS_V=1'}<=set(positive['model']['params'])
    for record in [positive['model'],positive['pipeline_model'],irq['model'],negative['model']]:model(record)
    assert positive['pipeline_model']['top']=='rv23_vector_scalar_overlap_tb'
    assert irq['model']['top']=='rv23_vector_scalar_irq_tb'
    for wrapper in ['tb/rv23_vector_scalar_overlap_tb.sv','tb/rv23_vector_scalar_irq_tb.sv']:
        text=(ROOT/wrapper).read_text(encoding='utf-8')
        assert all(flag in text for flag in ['.XLEN(64)','.HAS_H(1)','.HAS_V(1)'])
    folder=ROOT/'out/rva23/vector_scalar_overlap'
    for name,key in [('test.elf','elf_sha256'),('commit.csv','trace_sha256'),('sail.csv','sail_trace_sha256'),('observed.csv','pipeline_trace_sha256')]:
        assert sha(folder/name)==positive[key],name
    for phase in ['compile','run','sail','pipeline_run']:step(positive[phase])
    reference=read_csv(folder/'sail.csv')
    for name in ['commit.csv','observed.csv']:
        events,mismatch=compare(reference,read_csv(folder/name))
        assert mismatch is None and events==positive['outcomes']['matched_events']
    rows=read_csv(folder/'observed.csv')
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert len(traps)==1 and int(traps[0]['cause'])==2
    log=step(positive['pipeline_run'])
    match=re.search(r'VECTOR_SCALAR_OVERLAP int=(\d+) fp=(\d+) fp_coretire=(\d+) busy_start=(\d+) branch_keep=(\d+)',log)
    assert match and all(int(v)>0 for v in match.groups())
    observed=dict(zip(['int','fp','fp_coretire','busy_start','branch_keep'],map(int,match.groups())))
    assert positive['pipeline']==observed
    groups=defaultdict(dict)
    for row in rows:
        if row['trap']=='0':groups[row['cycle']][int(row['lane'])]=row
    coretires=sum(0 in group and 1 in group and int(group[0]['instruction'],16)&127==0x57 and
        group[1]['rd_fp']=='1' and group[1]['rd_write']=='1' for group in groups.values())
    assert coretires==observed['fp_coretire']

    assert irq['driver_sha256']==sha(ROOT/'scripts/run_vector_scalar_irq.py')
    assert irq['inputs']==source_inputs(irq['inputs'])
    folder=ROOT/'out/rva23/vector_scalar_irq'
    assert sha(folder/'test.elf')==irq['elf_sha256'] and sha(folder/'commit.csv')==irq['trace_sha256']
    step(irq['compile']);log=step(irq['run'])
    match=re.search(r'VECTOR_SCALAR_IRQ start=(\d+) pending=(\d+) retire=(\d+) trap=(\d+) overlap=(\d+)',log)
    assert match
    start,pending,retire,trap,overlap=map(int,match.groups())
    assert start<pending<retire<trap and overlap>0
    assert irq['cycles']==dict(start=start,pending=pending,retire=retire,trap=trap) and irq['scalar_overlap']==overlap
    symbols=subprocess.check_output([str(GCC/'riscv-none-elf-nm.exe'),'-n',str(folder/'test.elf')],text=True)
    pc=int(re.search(r'^([\da-f]+) \w irq_vector$',symbols,re.M)[1],16)
    rows=read_csv(folder/'commit.csv')
    vector=[r for r in rows if int(r['pc'],16)==pc and r['trap']=='0']
    traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
    assert len(vector)==len(traps)==1 and int(traps[0]['cause'])==11 and int(traps[0]['tval'],16)==0
    assert int(traps[0]['cycle'])-int(vector[0]['cycle'])==trap-retire

    assert negative['driver_sha256']==sha(ROOT/'scripts/check_vector_system_wake_negative.py')
    assert negative['positive_report_sha256']==sha(ROOT/paths[0])
    assert negative['kind']=='isolated_zero_data_mutant' and negative['expected_failure']
    assert negative['elf_sha256']==positive['elf_sha256']
    backend=ROOT/'rtl/backend/rv_backend.sv'
    assert negative['production_backend_sha256']==sha(backend)
    anchor='direct_wake_data[DIRECT_BYPASS_PORTS]  = system_wake_data_q;'
    text=backend.read_text(encoding='utf-8');assert text.count(anchor)==1
    mutant='out/negative_controls/vector_system_wake/zero_system_wake.sv'
    assert (ROOT/mutant).read_text(encoding='utf-8')==text.replace(anchor,"direct_wake_data[DIRECT_BYPASS_PORTS]  = '0;")
    expected=dict(positive['model']['inputs']);del expected['rtl/backend/rv_backend.sv'];expected[mutant]=sha(ROOT/mutant)
    assert negative['model']['inputs']==expected and negative['model']['params']==positive['model']['params']
    log=step(negative['run'],negative=True)
    assert negative['run']['expected_failure']=='g_lsu_base_cache_contract' and 'g_lsu_base_cache_contract' in log
    dump(ROOT/'out/rva23/vector_scalar_overlap_audit.json',dict(passed=True,complete_profile_validation=False,
        scope='Current-source directed scalar/vector overlap, precise recovery/IRQ and one isolated wake-data RTL mutant; not exhaustive RVWMO/profile validation',
        audit_sha256=sha(__file__),reports={p:sha(ROOT/p) for p in paths},
        matched_events=positive['outcomes']['matched_events'],pipeline=observed,irq_cycles=irq['cycles'],
        negative_controls=1))
    print('PASS current-source scalar/vector overlap: native/Sail, FP co-retire, precise IRQ and zero-data RTL mutant',flush=True)

if __name__=='__main__':main()

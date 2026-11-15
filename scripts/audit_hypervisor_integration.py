"""Fail closed on stale native H/HPM inputs, runtime artifacts or traces.

This is an implemented-feature checkpoint, not complete RVA23 compliance.
"""
import csv,json
from sim_runner import ROOT,sha,dump,source_inputs

def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
def fresh(inputs):
    for p,h in inputs.items():assert sha(ROOT/p)==h,('changed input',p)
def run(record):
    assert record['passed'] and record['exit_code']==0,record
    assert sha(ROOT/record['log'])==record['log_sha256'],record['log']
def model(record):
    fresh(record['inputs'])
    assert sha(ROOT/record['binary'])==record['binary_sha256'],record['binary']
    run(record['compile']);run(record['build'])

cases=[
    ('hypervisor_integration','rv64_hypervisor_basic.S','run_hypervisor_integration.py','48595031',[10,22,22,10]),
    ('hypervisor_gstage_integration','rv64_hypervisor_gstage.S','run_hypervisor_gstage_integration.py','48595032',[10,23,20,22,22,10]),
    ('hypervisor_interrupt_integration','rv64_hypervisor_interrupts.S','run_hypervisor_interrupt_integration.py','48595033',[10,2,6,22,22,8]),
    ('hypervisor_access_integration','rv64_hypervisor_access.S','run_hypervisor_access_integration.py','48595034',[13,2,2,8]),
    ('hpm_integration','rv64_hpm_overflow.S','run_hpm_integration.py','48504d31',[13,13,10]),
    ('hypervisor_vector_faults','rv64_hypervisor_vector_faults.S','run_hypervisor_vector_faults.py','48595035',[23,10,21,10,23,23,10])]
files=(ROOT/'rtl/filelist.f').read_text().splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
inputs=source_inputs(files);evidence=[];common_binary=None
for name,source,script,marker,expected in cases:
    folder=f'out/rva23/{name}';report=read(folder+'/report.json')
    assert report['passed'],name
    assert report['model']['inputs']==inputs,name
    assert '-GHAS_H=1' in report['model']['params'] and '-GXLEN=64' in report['model']['params'],name
    model(report['model']);run(report['run']);fresh(report['runtime_inputs'])
    assert set(report['runtime_inputs'])=={'tb/fixtures/bootrom/bootrom_host_jump64.hex','sw/benchmarks/coremark/rv32_tim.ld'}
    if common_binary is None:common_binary=report['model']['binary_sha256']
    assert report['model']['binary_sha256']==common_binary,('different native core',name)
    assert sha(ROOT/'sw/tests'/source)==report['source_sha256'],source
    assert sha(ROOT/'scripts'/script)==report['generator_sha256'],script
    assert sha(ROOT/folder/'test.elf')==report['elf_sha256'],name
    assert sha(ROOT/folder/'commit.csv')==report['trace_sha256'],name
    text=(ROOT/report['run']['log']).read_text(encoding='utf-8')
    assert 'PASS rv32_program_tb' in text and 'ELF AXI readback PASS total=' in text and f'data=0x{marker}' in text,name
    with (ROOT/folder/'commit.csv').open(newline='') as stream:
        traps=[row for row in csv.DictReader(stream) if row['trap']=='1' and int(row['pc'],16)>=0x40000000]
    assert [int(row['cause']) for row in traps]==expected,name
    assert report['traps']==traps,name
    evidence.append({'case':name,'report_sha256':sha(ROOT/folder/'report.json'),'trap_causes':expected})

folder='out/rva23/privileged_instruction_matrix';report=read(folder+'/report.json')
assert report['passed'] and report['case_count']==390
assert report['model']['inputs']==inputs and report['model']['binary_sha256']==common_binary
model(report['model']);run(report['compile']);run(report['run']);fresh(report['runtime_inputs'])
assert sha(ROOT/'scripts/run_privileged_instruction_matrix.py')==report['generator_sha256']
for name,key in [('test.S','source'),('cases.json','cases'),('test.elf','elf'),('commit.csv','trace')]:
    assert sha(ROOT/folder/name)==report[key+'_sha256']
cases=read(folder+'/cases.json');assert len(cases)==390
assert {row['mode'] for row in cases}=={'M','HS','VS','U','VU'}
assert sum(row['instruction'].startswith('pmp') for row in cases)==140
with (ROOT/folder/'commit.csv').open(newline='') as stream:
    traps=[row for row in csv.DictReader(stream) if row['trap']=='1' and int(row['pc'],16)>=0x80000000]
assert report['traps']==traps and [int(row['cause']) for row in traps]==report['expected_traps']
evidence.append({'case':'privileged_instruction_matrix','report_sha256':sha(ROOT/folder/'report.json'),
                 'case_count':390,'trap_count':len(traps)})

folder='out/rva23/hypervisor_breakpoint_metadata';report=read(folder+'/report.json')
assert report['passed'] and report['case_count']==33
assert report['model']['inputs']==inputs and report['model']['binary_sha256']==common_binary
model(report['model']);run(report['compile']);run(report['run']);fresh(report['runtime_inputs'])
assert sha(ROOT/'scripts/run_hypervisor_breakpoint_metadata.py')==report['generator_sha256']
for name,key in [('test.S','source'),('cases.json','cases'),('test.elf','elf'),('commit.csv','trace')]:
    assert sha(ROOT/folder/name)==report[key+'_sha256']
with (ROOT/folder/'commit.csv').open(newline='') as stream:
    traps=[row for row in csv.DictReader(stream) if row['trap']=='1' and int(row['pc'],16)>=0x80000000]
assert len(traps)==66 and report['traps']==traps
cases=read(folder+'/cases.json')
assert len(cases)==33 and {row['target'] for row in cases}=={'M','HS','VS'}
evidence.append({'case':'hypervisor_breakpoint_metadata','report_sha256':sha(ROOT/folder/'report.json'),
                 'case_count':33,'trap_count':len(traps)})

for path in ['out/rva23/hpm_counters.json','out/rva23/hpm_csr_file.json','out/rva23/hypervisor_csr_file.json']:
    report=read(path);assert report['passed'];model(report);run(report['run'])
    evidence.append({'component':path,'report_sha256':sha(ROOT/path)})
dump(ROOT/'out/rva23/hypervisor_checkpoint.json',{'passed':True,
    'scope':'Current H/Sha and HPM implementation: six native functional ELFs, a 390-case privileged matrix and 33 breakpoint metadata cases on one content-bound RV64 SoC plus committed CSR and counter components. No full ISA, timing or RV32 release sign-off.',
    'source_inputs':inputs,'binary_sha256':common_binary,'evidence':evidence,
    'audit_sha256':sha(__file__),'incomplete':['full architectural/differential validation','Zkt/Zvkt timing contract audit',
        'complete guest and concurrent-agent memory-ordering architectural coverage','renewed full RV32 release audit']})
print('PASS current H/HPM checkpoint: six native ELFs, 390 privilege cases, 33 breakpoint metadata cases, committed CSR/counter components and artifact binding',flush=True)

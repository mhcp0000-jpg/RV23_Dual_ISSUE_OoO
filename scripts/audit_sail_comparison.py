"""Bind pinned Sail, native host ABI, DUT config and same-ELF differential evidence."""
import json
import subprocess
import sys
from sim_runner import ROOT, sha, dump, source_inputs

def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))
def fresh(inputs):
    for name,digest in inputs.items():assert sha(ROOT/name)==digest,name
def execution(record):
    assert record['passed'] and record['exit_code']==0
    assert sha(ROOT/record['log'])==record['log_sha256']

folder='out/rva23/sail_upstream_comparison'
report=read(folder+'/report.json')
assert report['passed'] and not report['reference_only'] and len(report['cases'])==168
assert len({case['name'] for case in report['cases']})==168
fresh(report['inputs'])
model=report['model']
files=(ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
assert model['inputs']==source_inputs(files)
assert all(flag in model['params'] for flag in ['-GXLEN=64','-GHAS_H=1','-GHAS_V=1','-GHAS_MMU=1'])
assert sha(ROOT/model['binary'])==model['binary_sha256']
canonical=read('out/rva23/hypervisor_integration/model.json')
assert canonical['binary_sha256']==model['binary_sha256']

reference=report['reference']
assert reference['passed'] and reference['model_commit']=='e5acebb04ff573e93203596486b831a5974117c3'
assert sha(ROOT/reference['binary'])==reference['binary_sha256']
for key,name in [('generator','scripts/build_sail_reference.py'),('wrapper','scripts/reference/sail_cygwin.sh'),
                 ('driver','scripts/reference/sail_bounded_driver.cpp'),('trace_driver','scripts/reference/sail_trace_callbacks.h')]:
    assert sha(ROOT/name)==reference[key+'_sha256'],name
for name,digest in reference['host_runtime_sha256'].items():assert sha(name)==digest,name
for stage in ['configure','build','driver_build','version']:execution(reference[stage])
build='out/reference/sail-riscv-0.16-cygwin/build/'
generated={build+name:digest for name,digest in reference['generated_inputs'].items()}
fresh(generated)
abi='out/reference/host_abi/report.json'
assert sha(ROOT/abi)==reference['host_abi_report_sha256']
abi_report=read(abi);assert abi_report['passed']
assert sha(ROOT/'scripts/check_sail_host_abi.py')==abi_report['generator_sha256']
abi_inputs={f'out/reference/host_abi/{name}':abi_report[key+'_sha256'] for name,key in [('check.c','source'),('check.exe','binary')]}
fresh(abi_inputs)
for stage in ['compile','run']:execution(abi_report[stage])

config_report=read('out/reference/sail_config_provenance.json')
assert config_report['passed'] and config_report['reference_binary_sha256']==reference['binary_sha256']
assert config_report['config_sha256']==sha(ROOT/'config/reference/sail-rv23.json')
assert config_report['generator_sha256']==sha(ROOT/'scripts/prepare_sail_config.py')
execution(config_report['validation'])
config=read('config/reference/sail-rv23.json')
assert config['base']['xlen']==64 and config['memory']['physaddr_bits']==32
assert config['memory']['pmp']['count']==16 and config['memory']['pmp']['usable_count']==8
assert config['extensions']['H']['supported'] and config['extensions']['V']['vlen_exp']==7

for case in report['cases']:
    assert case['reference_passed'] and case['rtl_passed'] and case['inputs']==report['inputs']
    assert case['reference_binary_sha256']==reference['binary_sha256']
    assert case['rtl_model_sha256']==model['binary_sha256']
    for key in ['elf','sail_log','sail_trace','rtl_trace']:
        assert sha(ROOT/case[key])==case[key+'_sha256'],(case['name'],key)
    for stage in ['compile','rtl']:execution(case[stage])
    assert 'PASS Sail HTIF' in (ROOT/case['sail_log']).read_text(encoding='utf-8')

subprocess.run([sys.executable,str(ROOT/'scripts/audit_sail_retirements.py')],cwd=ROOT,check=True)
retirements=read(folder+'/retirement_audit.json')
assert retirements['passed'] and len(retirements['cases'])==152
negative_path='out/negative_controls/sail_retirement_checker_20261102/report.json'
negative=read(negative_path)
assert negative['passed'] and negative['audit_sha256']==sha(ROOT/'scripts/audit_sail_retirements.py')
assert negative['generator_sha256']==sha(ROOT/'scripts/run_sail_retirement_negative.py')
assert negative['original_report_sha256']==sha(ROOT/folder/'report.json')
for key in ['original_trace','corrupted_trace','input_report','rejected_report']:
    assert sha(ROOT/negative[key])==negative[key+'_sha256']
assert negative['run']['passed'] and negative['run']['exit_code']!=0
assert sha(ROOT/negative['run']['log'])==negative['run']['log_sha256']

evidence_path='out/rva23/sail_reference_evidence.json'
vendor=ROOT/'third_party/sail-riscv'
if (vendor/'.git').exists():
    assert subprocess.check_output(['git','-C',str(vendor),'rev-parse','HEAD'],text=True).strip()==reference['model_commit']
    assert not subprocess.check_output(['git','-C',str(vendor),'diff','--name-only'],text=True).strip()
    tracked=subprocess.check_output(['git','-C',str(vendor),'ls-files','--recurse-submodules'],text=True).splitlines()
    sources={('third_party/sail-riscv/'+name):sha(vendor/name) for name in tracked
             if (vendor/name).is_file() and not (vendor/name).is_symlink()
             and ((vendor/name).suffix in ['.sail','.sail_project','.cpp','.c','.h','.cmake','.in']
                  or (vendor/name).name in ['CMakeLists.txt','LICENSE','LICENSE.txt','LICENSE.md','LICENCE','COPYING','.gitmodules'])}
else:
    sources=read(evidence_path)['reference_source_inputs']
fresh(sources)
dump(ROOT/evidence_path,dict(passed=True,
    scope='168 identical functional ELFs pass official Sail model and current H/V RTL; exact 152 user-test retirement prefixes, excluding boot/HTIF tails. No full ACT4 certification, vector-state differential proof, cycle comparison or complete profile sign-off.',
    generator_sha256=sha(__file__),rtl_inputs=model['inputs'],rtl_binary_sha256=model['binary_sha256'],
    reference_binary_sha256=reference['binary_sha256'],reference_source_inputs=sources,generated_source_inputs=generated,
    host_abi_report=abi,host_abi_report_sha256=sha(ROOT/abi),host_abi_inputs=abi_inputs,
    tool_provenance_inputs={name:sha(ROOT/name) for name in [
        'out/reference/sail_compiler_download.json','out/reference/cygwin/setup_report.json']},
    comparison_report=folder+'/report.json',comparison_report_sha256=sha(ROOT/folder/'report.json'),
    retirement_report=folder+'/retirement_audit.json',retirement_report_sha256=sha(ROOT/folder/'retirement_audit.json'),
    config_report='out/reference/sail_config_provenance.json',config_report_sha256=sha(ROOT/'out/reference/sail_config_provenance.json'),
    negative_report=negative_path,negative_report_sha256=sha(ROOT/negative_path),
    upstream_elfs=168,exact_user_elfs=152,retirements_compared=retirements['retirements_compared']))
print('PASS pinned Sail/RTL evidence: 168 identical ELFs; 152 exact user traces;',retirements['retirements_compared'],'retirements',flush=True)

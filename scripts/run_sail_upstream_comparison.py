"""Run the exact same upstream functional ELF on official Sail and the H/V RTL."""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
from pathlib import Path
from sim_runner import ROOT, Simulator, GCC, sha, dump, source_inputs

parser = argparse.ArgumentParser()
parser.add_argument('--case')
parser.add_argument('--reference-only', action='store_true')
parser.add_argument('--resume', action='store_true')
args = parser.parse_args()
vendor = ROOT/'third_party/riscv-tests'
pins = {'tests':'3df703cd52d5f0d8224e3c50bf03c6cb70efff98',
        'env':'6de71edb142be36319e380ce782c3d1830c65d68'}
for key, path in [('tests',vendor),('env',vendor/'env')]:
    assert subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()==pins[key]
    assert not subprocess.check_output(['git','-C',str(path),'diff','--name-only'],text=True).strip()
reference_report = ROOT/'out/reference/sail-riscv-0.16-cygwin/build_report.json'
reference = json.loads(reference_report.read_text(encoding='utf-8'))
assert reference['passed']
reference_binary = ROOT/reference['binary']
assert sha(reference_binary)==reference['binary_sha256']
config = ROOT/'config/reference/sail-rv23.json'
linker = ROOT/'scripts/reference/upstream_htif.ld'
inputs = {p.relative_to(ROOT).as_posix():sha(p) for parent in [vendor/'isa',vendor/'env']
          for p in parent.rglob('*') if p.is_file() and p.suffix in ['.S','.h','.ld']}
for path in [config,linker,reference_report,Path(__file__).resolve(),vendor/'LICENSE',vendor/'env/LICENSE']:
    inputs[path.relative_to(ROOT).as_posix()] = sha(path)
inputs['tb/fixtures/bootrom/bootrom_host_jump64.hex']=sha(ROOT/'tb/fixtures/bootrom/bootrom_host_jump64.hex')
names = []
for suite in ['rv64ui','rv64um','rv64ua','rv64uf','rv64ud','rv64uc','rv64uzba','rv64uzbb','rv64uzbs','rv64uzicond']:
    makefrag = vendor/'isa'/suite/'Makefrag'
    inputs[makefrag.relative_to(ROOT).as_posix()] = sha(makefrag)
    match = re.search(r'^'+suite+r'_sc_tests\s*=\s*\\\n((?:[^\n]*\\\n)+)',makefrag.read_text(encoding='utf-8'),re.M)
    assert match, suite
    names.extend(suite+'/'+name for name in match[1].replace('\\',' ').split())
names += ['rv64mi/'+name for name in ['csr','mcsr','illegal','ma_fetch','scall','sbreak','zicntr','instret_overflow','pmpaddr']]
names += ['rv64si/'+name for name in ['csr','dirty','icache-alias','ma_fetch','scall','wfi','sbreak']]
if args.case:
    assert args.case in names
    names = [args.case]
model = None
if not args.reference_only:
    model = json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    assert all(flag in model['params'] for flag in ['-GXLEN=64','-GHAS_H=1','-GHAS_V=1','-GHAS_MMU=1'])
    files = (ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()+[
        'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
    assert model['inputs']==source_inputs(files)
    assert sha(ROOT/model['binary'])==model['binary_sha256']
folder = ROOT/'out/rva23/sail_upstream_comparison'
folder.mkdir(parents=True,exist_ok=True)
report_path = folder/('selected_report.json' if args.case else 'reference_report.json' if args.reference_only else 'report.json')
report = dict(passed=False, inputs=inputs, pins=pins, reference=reference, model=model,
              scope='Identical functional ELF and upstream self-checks on independent Sail/RTL; no cycle comparison or ACT4 certification',
              reference_only=args.reference_only, selected=names, cases=[])
dump(report_path,report)
with Simulator() as sim:
    reference_env = sim.env.copy()
    reference_env['PATH'] = 'C:/rv_toolchains/cygwin-rv23/bin;'+os.environ['PATH']
    def one(name):
        case_folder=folder/name
        case_folder.mkdir(parents=True,exist_ok=True)
        path=case_folder/'report.json'
        saved=json.loads(path.read_text(encoding='utf-8')) if args.resume and path.exists() else {}
        elf=case_folder/'test.elf'
        if not (saved.get('inputs')==inputs and saved.get('reference_passed') and
                elf.exists() and sha(elf)==saved.get('elf_sha256')):
            compile_record,_=sim.run([GCC/'riscv-none-elf-gcc.exe',
                '-march=rv64gcvh_zba_zbb_zbs_zicond','-mabi=lp64d','-mcmodel=medany',
                '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
                '-I'+str(vendor/'env/p'),'-I'+str(vendor/'env'),'-I'+str(vendor/'isa/macros/scalar'),
                '-T',linker,vendor/'isa'/(name+'.S'),'-o',elf],case_folder/'compile.log',60)
            ref_log=case_folder/'sail.log'
            ref_trace=case_folder/'sail_commit.csv'
            command=[str(reference_binary),'--config',str(config),'--trace','--commit-csv',str(ref_trace),
                     '--inst-limit','1000000',str(elf)]
            with ref_log.open('w',encoding='utf-8') as stream:
                result=subprocess.run(command,cwd=ROOT,env=reference_env,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
            output=ref_log.read_text(encoding='utf-8',errors='replace')
            if result.returncode or 'PASS Sail HTIF' not in output:
                raise RuntimeError('Sail '+name+': '+output[-1800:])
            saved=dict(name=name,inputs=inputs,elf=elf.relative_to(ROOT).as_posix(),elf_sha256=sha(elf),
                reference_passed=True,compile=compile_record,sail_log=ref_log.relative_to(ROOT).as_posix(),
                sail_log_sha256=sha(ref_log),reference_binary_sha256=sha(reference_binary),
                sail_trace=ref_trace.relative_to(ROOT).as_posix(),sail_trace_sha256=sha(ref_trace))
            dump(path,saved)
        else:
            assert sha(ROOT/saved['sail_log'])==saved['sail_log_sha256']
            assert sha(ROOT/saved['sail_trace'])==saved['sail_trace_sha256']
        if model is not None:
            trace=case_folder/'rtl_commit.csv'
            run,output=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
                f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit','+htif',
                '+timeout_cycles=1000000','+expected_exit_code=0'],case_folder/'rtl.log',240)
            assert 'PASS rv32_program_tb' in output
            saved.update(rtl_passed=True,rtl_model_sha256=model['binary_sha256'],rtl=run,
                         rtl_trace=trace.relative_to(ROOT).as_posix(),rtl_trace_sha256=sha(trace))
            dump(path,saved)
        return saved
    failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        pending={pool.submit(one,name):name for name in names}
        for future in concurrent.futures.as_completed(pending):
            name=pending[future]
            try:
                result=future.result();report['cases'].append(result)
                print('PASS Sail'+('/RTL' if model else ''),name,flush=True)
            except Exception as error:
                failures.append(name);report['cases'].append(dict(name=name,passed=False,error=str(error)))
                print('FAIL Sail'+('/RTL' if model else ''),name,str(error)[-220:],flush=True)
            dump(report_path,report)
    for name,digest in inputs.items():assert sha(ROOT/name)==digest,name
    assert sha(reference_binary)==reference['binary_sha256']
    if model:
        for name,digest in model['inputs'].items():assert sha(ROOT/name)==digest,name
        assert sha(ROOT/model['binary'])==model['binary_sha256']
    report['passed']=not failures
    report['cases'].sort(key=lambda item:item['name'])
    dump(report_path,report)
    assert not failures,failures
print('PASS same-ELF independent reference checks',len(names),flush=True)

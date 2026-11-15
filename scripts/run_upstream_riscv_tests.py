"""Run pinned, unmodified upstream self-checking ISA tests on the RV64 SoC.

The physical environment's tohost transport is adapted to the existing host
MMIO device. No instruction test or expected result is changed. This suite is
independent regression evidence, not ACT4 certification or a Sail comparison.
"""
import argparse,concurrent.futures,json,re,subprocess
from sim_runner import ROOT,Simulator,GCC,sha,dump,source_inputs

parser=argparse.ArgumentParser()
parser.add_argument('--case',help='one suite/name, for example rv64ui/add')
parser.add_argument('--jobs',type=int,default=2)
parser.add_argument('--resume',action='store_true')
args=parser.parse_args()
vendor=ROOT/'third_party/riscv-tests'
pins={'tests':'3df703cd52d5f0d8224e3c50bf03c6cb70efff98','env':'6de71edb142be36319e380ce782c3d1830c65d68'}
for name,path in [('tests',vendor),('env',vendor/'env')]:
    assert subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()==pins[name]
    assert not subprocess.check_output(['git','-C',str(path),'diff','--name-only'],text=True).strip()

folder=ROOT/'out/rva23/upstream_riscv_tests';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
assert '-GHAS_H=1' in model['params'] and '-GXLEN=64' in model['params']
files=(ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
assert model['inputs']==source_inputs(files)
runtime={p:sha(ROOT/p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex','sw/benchmarks/coremark/rv32_tim.ld']}
upstream={p.relative_to(ROOT).as_posix():sha(p) for base in [vendor/'isa',vendor/'env'] for p in base.rglob('*')
          if p.is_file() and p.suffix in ['.S','.h','.ld']}
upstream['third_party/riscv-tests/LICENSE']=sha(vendor/'LICENSE')
upstream['third_party/riscv-tests/env/LICENSE']=sha(vendor/'env/LICENSE')
for name in ['rv64ui','rv64um','rv64ua','rv64uf','rv64ud','rv64uc','rv64uzba','rv64uzbb','rv64uzbs','rv64uzicond']:
    upstream[f'third_party/riscv-tests/isa/{name}/Makefrag']=sha(vendor/'isa'/name/'Makefrag')

header=(vendor/'env/p/riscv_test.h').read_text(encoding='utf-8')
header=header.replace('#include "../encoding.h"','#include "encoding.h"')
old='        sw TESTNUM, tohost, t5;                                         \\\n        sw zero, tohost + 4, t5;                                        \\'
# Keep literal assembler macro continuations on every replacement line.
new='\n'.join(line.rstrip().rstrip('\\').rstrip()+' \\' for line in [
    '        li t5, 0x10000000;','        sw TESTNUM, 0xc(t5);',
    '        addi t6, TESTNUM, -1;','        snez t6, t6;','        sw t6, 0x14(t5);'])
assert header.count(old)==1,'upstream physical environment transport changed'
header=header.replace(old,new)
adapted=folder/'include/riscv_test.h';adapted.parent.mkdir(exist_ok=True)
adapted.write_text(header,encoding='utf-8')
bound={**model['inputs'],**runtime,**upstream,
       adapted.relative_to(ROOT).as_posix():sha(adapted),
       'scripts/run_upstream_riscv_tests.py':sha(__file__)}
def fresh():
    for p,h in bound.items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()

names=[]
for suite in ['rv64ui','rv64um','rv64ua','rv64uf','rv64ud','rv64uc','rv64uzba','rv64uzbb','rv64uzbs','rv64uzicond']:
    text=(vendor/'isa'/suite/'Makefrag').read_text(encoding='utf-8')
    match=re.search(r'^'+suite+r'_sc_tests\s*=\s*\\\n((?:[^\n]*\\\n)+)',text,re.M)
    assert match,suite
    names.extend(suite+'/'+name for name in match[1].replace('\\',' ').split())
if args.case:
    # Privileged tests can also be selected explicitly; their assumptions must
    # be reviewed individually (e.g. Svadu, misalignment traps or Sdtrig).
    assert re.fullmatch(r'rv64[a-z0-9]+/[a-z0-9_-]+',args.case)
    assert (vendor/'isa'/(args.case+'.S')).is_file()
    names=[args.case]

report_path=folder/('report.json' if not args.case else 'selected_report.json')
report=dict(passed=False,scope='Pinned upstream self-checking RV64 I/M/A/F/D/C/B/Zicond tests; host transport only adapted; no ACT4 certification',
            repository='https://github.com/riscv-software-src/riscv-tests',pins=pins,model=model,
            inputs=bound,compiler_sha256=sha(GCC/'riscv-none-elf-gcc.exe'),selected=names,cases=[])
dump(report_path,report)
with Simulator() as sim:
    def run_case(name):
        case_folder=folder/name;case_folder.mkdir(parents=True,exist_ok=True)
        case_path=case_folder/'report.json'
        if args.resume and case_path.exists():
            saved=json.loads(case_path.read_text(encoding='utf-8'))
            if saved['passed'] and saved['inputs']==bound and saved['binary_sha256']==model['binary_sha256']:
                artifacts=[(saved[k],saved[k+'_sha256']) for k in ['elf','trace']]
                artifacts.extend((saved[k]['log'],saved[k]['log_sha256']) for k in ['compile','run'])
                if all(sha(ROOT/p)==h for p,h in artifacts):return saved
        source=vendor/'isa'/(name+'.S');elf=case_folder/'test.elf';trace=case_folder/'commit.csv'
        compile_record,_=sim.run([GCC/'riscv-none-elf-gcc.exe',
            '-march=rv64gcvh_zba_zbb_zbs_zicond','-mabi=lp64d','-mcmodel=medany',
            '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
            '-I'+str(adapted.parent),'-I'+str(vendor/'env'),'-I'+str(vendor/'isa/macros/scalar'),
            '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],case_folder/'compile.log',60)
        try:
            run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
                f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
                '+timeout_cycles=1000000','+expected_exit_code=0'],case_folder/'simulation.log',240)
            assert 'PASS rv32_program_tb' in text and 'data=0x00000001' in text
        except Exception as error:
            dump(case_path,dict(passed=False,name=name,error=str(error)))
            raise
        result=dict(passed=True,name=name,inputs=bound,binary_sha256=model['binary_sha256'],
                    elf=elf.relative_to(ROOT).as_posix(),elf_sha256=sha(elf),
                    trace=trace.relative_to(ROOT).as_posix(),trace_sha256=sha(trace),compile=compile_record,run=run)
        dump(case_path,result);return result
    failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(4,args.jobs))) as pool:
        pending={pool.submit(run_case,name):name for name in names}
        for future in concurrent.futures.as_completed(pending):
            name=pending[future]
            try:
                result=future.result();report['cases'].append(result)
                print('PASS upstream',name,flush=True)
            except Exception as error:
                failures.append(name);report['cases'].append(dict(passed=False,name=name,error=str(error)))
                print('FAIL upstream',name,str(error)[-180:],flush=True)
            dump(report_path,report)
    fresh()
    report['cases'].sort(key=lambda row:row['name']);report['passed']=not failures
    dump(report_path,report)
    assert not failures,failures
print(f'PASS upstream self-checking ISA tests {len(names)}/{len(names)} on one current H-enabled RV64 SoC',flush=True)

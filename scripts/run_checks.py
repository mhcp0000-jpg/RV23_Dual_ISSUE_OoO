from pathlib import Path
from sim_runner import DEV, GCC, VER, Simulator, source_inputs
import argparse, hashlib, json, os, shutil, subprocess, sys, time
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
ap=argparse.ArgumentParser()
ap.add_argument('--lint-only',action='store_true')
ap.add_argument('--memory-only',action='store_true')
ap.add_argument('--boot-only',action='store_true')
ap.add_argument('--cache-only',action='store_true')
args=ap.parse_args()
out=ROOT/'out';out.mkdir(exist_ok=True)
def run(command,log,env=None,timeout=600):
    started=time.time()
    with open(out/log,'w',encoding='utf-8') as f:
        p=subprocess.run([str(x) for x in command],stdout=f,stderr=subprocess.STDOUT,
                         env=env,timeout=timeout)
    if p.returncode:
        print((out/log).read_text(encoding='utf-8',errors='replace')[-7000:])
        raise RuntimeError(f'{log}: exit {p.returncode}')
    print(f'PASS {log} {time.time()-started:.1f}s',flush=True)
run([sys.executable,'scripts/check_rtl.py'],'check_rtl_runner.log',timeout=60)
if args.lint_only: sys.exit(0)
sources=Path('rtl/filelist.f').read_text().splitlines()
report={'passed':False,'requested_passed':False,'results':[],
    'scope':'Directed subsystem regression and RV32 boot smoke; not ISA/profile certification',
    'source_sha256':source_inputs(sources)}
for prior in ['memory_verification.json','verification.json']:
    path=out/prior
    if path.exists():
        old=json.loads(path.read_text(encoding='utf-8'))
        if old.get('source_sha256') == report['source_sha256']:
            for result in old.get('results',[]):
                if result.get('passed'):
                    report['results']=[r for r in report['results'] if r['top']!=result['top']]
                    report['results'].append(result)
def check(sim):
    drive, env = sim.drive, sim.env

    def simulate(top,files,defines=()):
        build=Path(drive+'/out/'+top);build.mkdir(parents=True,exist_ok=True)
        run([VER,'--cc','--exe','--main','--timing','--assert','-Wno-fatal',
             '--output-split','15000','--top-module',top,'--Mdir',build,
             *defines,*[drive+'/'+f for f in files]],top+'_verilator.log',env,120)
        run([DEV/'make.exe','-C',build,'-f','V'+top+'.mk','-j2',
             'CXX=g++','CC=gcc','LINK=g++'],top+'_build.log',env,600)
        run([build/('V'+top+'.exe')],top+'_simulation.log',env,60)
        log=(out/(top+'_simulation.log')).read_text(encoding='utf-8',errors='replace')
        if f'PASS {top}' not in log: raise RuntimeError('Missing simulation PASS')
        report['results']=[r for r in report['results'] if r['top']!=top]
        report['results'].append({'top':top,'passed':True,'summary':
            next(l for l in log.splitlines() if f'PASS {top}' in l),
            'test_sha256':hashlib.sha256(Path('tb/'+top+'.sv').read_bytes()).hexdigest(),
            'binary_sha256':hashlib.sha256((build/('V'+top+'.exe')).read_bytes()).hexdigest()})
    if not args.boot_only and not args.cache_only:
        memory_sources=[s for s in sources if not s.startswith('rtl/backend/') and
            not s.startswith('rtl/frontend/') and s not in
            ['rtl/rv_ooo_core.sv','rtl/soc/rv23_core.sv','rtl/soc/rv23_soc_top.sv']]
        simulate('rv23_memory_tb',memory_sources+['tb/rv23_memory_tb.sv'])
    if not args.memory_only and not args.boot_only:
        simulate('rv23_cache_fault_tb',
            ['rtl/soc/rv_soc_pkg.sv','rtl/soc/rv23_pkg.sv','rtl/rv_ooo_pkg.sv',
             'rtl/soc/rv_local_mem_if.sv','rtl/soc/rv23_cache.sv','tb/rv23_cache_fault_tb.sv'])
    if not args.memory_only and not args.cache_only:
        prefix='riscv-none-elf-'
        cc=GCC/(prefix+'gcc.exe')
        run([cc,'-march=rv32imfc_zicsr_zifencei','-mabi=ilp32f','-nostdlib',
             '-Wl,--no-relax','-T','sw/link.ld','sw/boot_smoke.S','-o','out/boot.elf'],
             'boot_assemble.log',env,30)
        run([GCC/(prefix+'objcopy.exe'),'-O','binary','out/boot.elf','out/boot.bin'],
             'boot_objcopy.log',env,30)
        data=Path('out/boot.bin').read_bytes()
        data+=bytes((-len(data))%8)
        Path('out/boot.hex').write_text('\n'.join(f'{int.from_bytes(data[i:i+8],"little"):016x}'
            for i in range(0,len(data),8))+'\n')
        nm=subprocess.check_output([str(GCC/(prefix+'nm.exe')),'out/boot.elf'],text=True)
        done=int(next(l.split()[0] for l in nm.splitlines() if l.endswith(' done')),16)
        simulate('rv23_boot_tb',sources+['tb/rv23_boot_tb.sv'],
                 [f'+define+DONE_ROW={(done-0x80000000)//8}',f'+define+DONE_SHIFT={(done%8)*8}'])
    report['requested_passed']=True
    report['passed']={'rv23_memory_tb','rv23_cache_fault_tb','rv23_boot_tb'} <= {
        r['top'] for r in report['results'] if r.get('passed')}

try:
    with Simulator() as sim:
        check(sim)
except Exception as error:
    report['failure']=str(error)
    raise
finally:
    Path('out/verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report['results'],indent=2))

"""Bounded native RTL simulations with content-bound result records."""
from pathlib import Path
import hashlib,json,os,subprocess,time

ROOT=Path(__file__).resolve().parents[1]
VER_ROOT=Path('C:/rv_toolchains/verilator-5.050')
VER=VER_ROOT/'bin/verilator_bin.exe'
DEV=Path('C:/rv_toolchains/w64devkit-2.9.1/w64devkit/bin')
GCC=Path('C:/rv_toolchains/xpack-riscv-none-elf-gcc-15.2.0-1/bin')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

class Simulator:
    def __enter__(self):
        os.chdir(ROOT)
        self.env=os.environ.copy();self.env['VERILATOR_ROOT']=str(VER_ROOT)
        self.env['PATH']=str(DEV)+';'+self.env['PATH']
        self.drive=next((f'{d}:' for d in 'ZYXWUTSR' if not Path(f'{d}:/').exists()),None)
        if not self.drive:raise RuntimeError('No unused ASCII workspace alias')
        subprocess.run(['subst',self.drive,str(ROOT)],check=True)
        return self
    def __exit__(self,*args):subprocess.run(['subst',self.drive,'/d'],check=False)
    def run(self,command,log,timeout=600,expected_failure=None):
        log=Path(log);log.parent.mkdir(parents=True,exist_ok=True)
        started=time.time()
        with log.open('w',encoding='utf-8') as f:
            p=subprocess.run([str(x) for x in command],cwd=ROOT,env=self.env,
                stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
        text=log.read_text(encoding='utf-8',errors='replace')
        if expected_failure:
            passed=p.returncode!=0 and expected_failure in text
        else:passed=p.returncode==0
        record={'exit_code':p.returncode,'seconds':round(time.time()-started,3),
                'log':log.relative_to(ROOT).as_posix(),'log_sha256':sha(log),
                'expected_failure':expected_failure,'passed':passed}
        if not passed:raise RuntimeError(f'{log}: native={p.returncode}\n{text[-5000:]}')
        return record,text
    def build(self,name,top,files,params=()):
        build=ROOT/'out/regression'/name;build.mkdir(parents=True,exist_ok=True)
        # Native .d files can retain a previous ephemeral drive letter for
        # explicit C++ DPI inputs. Drop only generated dependency caches;
        # retain source, logs and binaries until the new build succeeds.
        for dependency in build.glob('*.d'):
            dependency.unlink()
        dpi_object=build/'elf_loader.o'
        if dpi_object.exists():dpi_object.unlink()
        mapped=self.drive+'/'+build.relative_to(ROOT).as_posix()
        inputs={p:sha(ROOT/p) for p in files}
        compile_record,_=self.run([VER,'--cc','--exe','--main','--timing','--assert',
            '-Wno-fatal','-Werror-UNOPTFLAT','--output-split','10000',
            '--top-module',top,'--Mdir',mapped,*params,
            *[self.drive+'/'+p for p in files]],build/'compile.log',120)
        build_record,_=self.run([DEV/'make.exe','-j2','-C',mapped,'-f',f'V{top}.mk',
            'CXX=g++','CC=gcc','LINK=g++'],build/'build.log',600)
        if any(sha(ROOT/p)!=h for p,h in inputs.items()):
            raise RuntimeError('RTL/TB changed during build; result cannot be accepted')
        return {'name':name,'top':top,'params':list(params),'inputs':inputs,
            'compile':compile_record,'build':build_record,
            'binary':f'out/regression/{name}/V{top}.exe',
            'binary_sha256':sha(build/f'V{top}.exe'),'passed':False}
    def simulate(self,record,args=(),label='simulation',timeout=120,expected_failure=None):
        path=ROOT/'out/regression'/record['name']/(label+'.log')
        result,text=self.run([ROOT/record['binary'],*args],path,timeout,expected_failure)
        if not expected_failure and 'PASS' not in text:
            raise RuntimeError('Successful exit without a PASS witness: '+str(path))
        return {**result,'args':list(args),'witnesses':[x for x in text.splitlines() if 'PASS' in x]}

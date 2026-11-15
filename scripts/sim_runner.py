"""Bounded native RTL simulations with content-bound result records."""
from pathlib import Path
import hashlib,json,os,re,subprocess,time

ROOT=Path(__file__).resolve().parents[1]
VER_ROOT=Path('C:/rv_toolchains/verilator-5.050')
VER=VER_ROOT/'bin/verilator_bin.exe'
DEV=Path('C:/rv_toolchains/w64devkit-2.9.1/w64devkit/bin')
GCC=Path('C:/rv_toolchains/xpack-riscv-none-elf-gcc-15.2.0-1/bin')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def source_inputs(files,dependencies=()):
    """Bind local HDL includes as well as compilation units to the model."""
    pending=list(files)+list(dependencies);inputs={}
    while pending:
        name=pending.pop(0);path=ROOT/name
        name=path.relative_to(ROOT).as_posix()
        if name in inputs:continue
        inputs[name]=sha(path)
        if path.suffix not in ['.sv','.v','.svh','.vh','.vi']:continue
        for include in re.findall(r'^\s*`include\s+"([^"]+)"',path.read_text(encoding='utf-8'),re.M):
            target=path.parent/include
            if not target.exists():target=ROOT/include
            if not target.exists():raise FileNotFoundError(f'{name}: {include}')
            pending.append(target.relative_to(ROOT).as_posix())
    return inputs
def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

class Simulator:
    def __enter__(self):
        os.chdir(ROOT)
        self.env=os.environ.copy();self.env['VERILATOR_ROOT']=str(VER_ROOT)
        self.env['PATH']=str(DEV)+';'+self.env['PATH']
        # Claim the alias atomically with SUBST itself. Checking Path.exists
        # first races with another independent regression starting concurrently.
        self.drive=None
        # A Linux replay can hold one alias while its model build claims
        # another alongside the independent regression runners.
        for letter in 'ZYXWVUTSRQPONM':
            candidate=f'{letter}:'
            if Path(candidate+'/').exists():continue
            claim=subprocess.run(['subst',candidate,str(ROOT)],capture_output=True)
            if claim.returncode==0:
                self.drive=candidate
                break
        if not self.drive:raise RuntimeError('No unused ASCII workspace alias')
        return self
    def __exit__(self,*args):subprocess.run(['subst',self.drive,'/d'],check=False)
    def run(self,command,log,timeout=600,expected_failure=None):
        log=Path(log);log.parent.mkdir(parents=True,exist_ok=True)
        timeout=max(1,round(timeout*float(self.env.get('RV23_HOST_TIMEOUT_SCALE','1'))))
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
                'expected_failure':expected_failure,'passed':passed,'host_timeout_seconds':timeout}
        if not passed:raise RuntimeError(f'{log}: native={p.returncode}\n{text[-5000:]}')
        return record,text
    def build(self,name,top,files,params=(),dependencies=()):
        build=ROOT/'out/regression'/name;build.mkdir(parents=True,exist_ok=True)
        # Native .d files can retain a previous ephemeral drive letter for
        # explicit C++ DPI inputs. Drop only generated dependency caches;
        # retain source, logs and binaries until the new build succeeds.
        for dependency in build.glob('*.d'):
            dependency.unlink()
        dpi_object=build/'elf_loader.o'
        if dpi_object.exists():dpi_object.unlink()
        mapped=self.drive+'/'+build.relative_to(ROOT).as_posix()
        inputs=source_inputs(files,dependencies)
        compile_record,_=self.run([VER,'--cc','--exe','--main','--timing','--assert',
            '-Wno-fatal','-Werror-UNOPTFLAT','--output-split','10000',
            '--top-module',top,'--Mdir',mapped,*params,
            *[self.drive+'/'+p for p in files]],build/'compile.log',120)
        build_record,_=self.run([DEV/'make.exe','-j4','-C',mapped,'-f',f'V{top}.mk',
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

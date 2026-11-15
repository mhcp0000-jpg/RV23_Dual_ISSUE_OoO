"""Install isolated, verified MSYS2 build dependencies for ACT4's Ruby gems."""
import json,subprocess,urllib.request,os
from pathlib import Path
from sim_runner import ROOT,DEV,sha,dump

url='https://github.com/msys2/msys2-installer/releases/download/2026-09-27/msys2-base-x86_64-20260927.tar.xz'
expected='ea2f31a0b6ade63914ce441ffb022f0f6aa96982bfefa2326460a26d5fb01322'
archive=Path('C:/rv_toolchains/downloads/msys2-base-x86_64-20260927.tar.xz')
folder=ROOT/'out/act4/setup';folder.mkdir(parents=True,exist_ok=True)
if not archive.exists() or sha(archive)!=expected:
    archive.write_bytes(urllib.request.urlopen(url,timeout=120).read())
assert sha(archive)==expected
target=Path('C:/rv_toolchains/msys-act4');target.mkdir(parents=True,exist_ok=True)
if not (target/'msys64/usr/bin/msys-2.0.dll').exists():
    env=os.environ.copy();env['PATH']='C:/rv_toolchains/cygwin-rv23/bin;'+env['PATH']
    subprocess.run(['C:/rv_toolchains/cygwin-rv23/bin/tar.exe','xf','/cygdrive/c/rv_toolchains/downloads/'+archive.name,'-C',
                    '/cygdrive/c/rv_toolchains/msys-act4'],check=True,timeout=180,env=env)
shell=target/'msys64/usr/bin/bash.exe'
with (folder/'msys_packages.log').open('w',encoding='utf-8') as stream:
    p=subprocess.run([str(shell),'--login','-c','pacman --noconfirm -S --needed mingw-w64-ucrt-x86_64-gcc make'],
        stdout=stream,stderr=subprocess.STDOUT,timeout=1800)
dump(folder/'msys_report.json',dict(passed=p.returncode==0,url=url,sha256=expected,
    generator_sha256=sha(__file__),exit_code=p.returncode,log_sha256=sha(folder/'msys_packages.log')))
assert p.returncode==0,(folder/'msys_packages.log').read_text(encoding='utf-8',errors='replace')[-2500:]
print('PASS isolated MSYS2 Ruby native-extension toolchain',flush=True)

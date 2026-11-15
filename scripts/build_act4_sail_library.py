"""Build ACT4's required official Sail 0.13.1 model without altering ISA sources."""
import os
import shutil
import subprocess
from pathlib import Path
from sim_runner import ROOT,Simulator,sha,dump

source=ROOT/'third_party/sail-riscv-act4'
commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
assert commit=='27224ccb2290f022e46213c05b3e72e8a9ea635e'
assert not subprocess.check_output(['git','-C',str(source),'diff','--name-only'],text=True).strip()
cygwin=Path('C:/rv_toolchains/cygwin-rv23/bin')
folder=ROOT/'out/act4/sail-0.13.1';folder.mkdir(parents=True,exist_ok=True)
prefix='/cygdrive/c/rv_workspaces/rv23'
build=prefix+'/out/act4/sail-0.13.1/build'
old=ROOT/'out/reference/sail-riscv-0.16-cygwin/build/model/sail_smt_cache'
cache=folder/'build/model/sail_smt_cache'
if old.exists() and not cache.exists():
    cache.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,cache)
report=dict(passed=False,commit=commit,version='0.13.1',generator_sha256=sha(__file__),
            scope='ACT4 required reference library build only; not a DUT test verdict')
path=folder/'library_report.json';dump(path,report)
with Simulator() as sim:
    sim.env['PATH']=str(cygwin)+';C:/rv_toolchains/sail-0.20.3/sail/bin;'+os.environ['PATH']
    try:
        report['configure'],_=sim.run([cygwin/'cmake.exe','-S',prefix+'/third_party/sail-riscv-act4',
            '-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CXX_FLAGS_RELEASE=-O1 -DNDEBUG',
            '-DCMAKE_C_COMPILER=/usr/bin/gcc','-DCMAKE_CXX_COMPILER=/usr/bin/g++',
            '-DSAIL_BIN='+prefix+'/scripts/reference/sail_cygwin.sh',
            '-DENABLE_RISCV_TESTS=OFF','-DFIRST_PARTY_TESTS=OFF'],folder/'configure.log',300)
        dump(path,report);print('CONFIGURED ACT4 required Sail 0.13.1',flush=True)
        report['build'],_=sim.run([cygwin/'cmake.exe','--build',build,'--target','riscv_model','-j2'],folder/'build.log',3600)
        report['artifacts']={p.relative_to(ROOT).as_posix():sha(p) for p in [
            folder/'build/c_emulator/libriscv_model.a',folder/'build/sail_runtime/libsail_runtime.a',
            folder/'build/dependencies/softfloat/libsoftfloat.a',folder/'build/sail_riscv_model.cpp',
            folder/'build/sail_riscv_model.h',folder/'build/sail_riscv_config_schema.json']}
        report['passed']=True
    finally:dump(path,report)
print('PASS pinned Sail 0.13.1 reference library for ACT4',flush=True)

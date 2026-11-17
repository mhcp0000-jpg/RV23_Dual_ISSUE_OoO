"""Run the official ACT4 build pipeline against the full RVA23S64 DUT config."""
import os,subprocess,sys
from sim_runner import ROOT

env=os.environ.copy()
env.update(PYTHONUTF8='1',BUNDLE_PATH='C:/rv_toolchains/act4-gems',
    RV23_ACT4_WINDOWS_IDL='1',
    XDG_CACHE_HOME='C:/rv_toolchains/act4-cache',XDG_DATA_HOME='C:/rv_toolchains/act4-data',
    MSYS2_PATH='C:/rv_toolchains/msys-act4/msys64',
    RUBYOPT='-rC:/rv_workspaces/rv23/scripts/reference/ruby_windows_tools.rb')
env['PATH']=';'.join([
    'C:/rv_toolchains/ruby-act4/rubyinstaller-3.4.10-1-x64/bin',
    'C:/rv_toolchains/z3-act4/z3-5.0.0-x64-win/bin',
    'C:/rv_toolchains/msys-act4/msys64/ucrt64/bin','C:/rv_toolchains/msys-act4/msys64/usr/bin',
    'C:/rv_toolchains/cygwin-rv23/bin',env['PATH']])
uv_python = ['--python', env['RV23_ACT4_PYTHON']] if 'RV23_ACT4_PYTHON' in env else []
command=['C:/rv_toolchains/uv-0.11.33/uv.exe','run','--no-dev',*uv_python,'python',
    'C:/rv_workspaces/rv23/scripts/act4_host_run.py',
    os.environ.get('RV23_ACT4_CONFIG','C:/rv_workspaces/rv23/config/act4/rv23/test_config.yaml'),
    '--workdir',os.environ.get('RV23_ACT4_WORKDIR','C:/rv_workspaces/rv23/out/act4/work'),*sys.argv[1:]]
folder=ROOT/'out/act4';folder.mkdir(parents=True,exist_ok=True)
log=folder/os.environ.get('RV23_ACT4_LOG','framework.log')
with log.open('w',encoding='utf-8') as stream:
    result=subprocess.run(command,cwd=env.get('RV23_ACT4_SOURCE_ROOT','C:/rv_workspaces/rv23/third_party/riscv-arch-test'),env=env,
                          stdout=stream,stderr=subprocess.STDOUT,timeout=14400)
print(log.read_text(encoding='utf-8',errors='replace')[-6500:],flush=True)
assert result.returncode==0,f'ACT4 framework failed; see {log}'
print('PASS ACT4 self-checking ELF generation (DUT execution is separate)',flush=True)

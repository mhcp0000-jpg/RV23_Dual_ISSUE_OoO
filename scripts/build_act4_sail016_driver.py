# SPDX-License-Identifier: Apache-2.0
"""Link ACT signature I/O to official Sail 0.16, which implements H."""
import json, os, subprocess
from pathlib import Path
from sim_runner import ROOT, Simulator, sha, dump

folder=ROOT/'out/act4/sail-0.16';folder.mkdir(parents=True,exist_ok=True)
library_path=ROOT/'out/reference/sail-riscv-0.16-cygwin/build_report.json'
library=json.loads(library_path.read_text(encoding='utf-8'))
assert library['passed'] and library['model_version']=='0.16'
src_root=ROOT/'third_party/sail-riscv'
assert subprocess.check_output(['git','-C',str(src_root),'rev-parse','HEAD'],text=True).strip()==library['model_commit']
assert not subprocess.check_output(['git','-C',str(src_root),'diff','--name-only'],text=True).strip()
prefix='/cygdrive/c/rv_workspaces/rv23';src=prefix+'/third_party/sail-riscv'
build=prefix+'/out/reference/sail-riscv-0.16-cygwin/build'
cygwin=Path('C:/rv_toolchains/cygwin-rv23/bin');binary=folder/'sail_act4_reference.exe'
report=dict(passed=False,scope='ACT4 test content with Sail 0.16 instead of required 0.13.1; compatibility validation, not official ACT4 certification',
    model_commit=library['model_commit'],model_version='0.16',library_report_sha256=sha(library_path),
    driver_sha256=sha(ROOT/'scripts/reference/act4_sail_driver.cpp'))
with Simulator() as sim:
    sim.env['PATH']=str(cygwin)+';'+os.environ['PATH']
    include=[src+'/c_emulator',src+'/dependencies/elfio',build,build+'/c_emulator',build+'/config',
        build+'/_deps/jsoncons-src/include',prefix+'/scripts/reference',
        '/cygdrive/c/rv_toolchains/sail-0.20.3/sail/share/sail/lib']
    report['compile'],_=sim.run([cygwin/'g++.exe','-std=gnu++17','-O1','-DACT4_SAIL_016',*['-I'+p for p in include],
        prefix+'/scripts/reference/act4_sail_driver.cpp',src+'/c_emulator/riscv_callbacks_log.cpp',
        build+'/c_emulator/libriscv_model.a',build+'/dependencies/softfloat/libsoftfloat.a',
        build+'/sail_runtime/libsail_runtime.a','-lgmp','-o',prefix+'/out/act4/sail-0.16/'+binary.name],folder/'driver_compile.log',180)
    report['version'],output=sim.run([binary,'--version'],folder/'driver_version.log',30)
    assert output.strip()=='0.16',output
    report.update(passed=True,binary=binary.relative_to(ROOT).as_posix(),binary_sha256=sha(binary))
dump(folder/'driver_report.json',report)
print('PASS genuine Sail 0.16 ACT signature driver; nonstandard ACT4 reference version',flush=True)

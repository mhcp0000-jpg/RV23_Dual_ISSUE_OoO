"""Link ACT4 signature I/O to the required, unmodified Sail 0.13.1 library."""
import json,os
from pathlib import Path
from sim_runner import ROOT,Simulator,sha,dump

folder=ROOT/'out/act4/sail-0.13.1'
library=json.loads((folder/'library_report.json').read_text(encoding='utf-8'))
assert library['passed'] and library['version']=='0.13.1'
for name,digest in library['artifacts'].items():assert sha(ROOT/name)==digest,name
prefix='/cygdrive/c/rv_workspaces/rv23';src=prefix+'/third_party/sail-riscv-act4';build=prefix+'/out/act4/sail-0.13.1/build'
cygwin=Path('C:/rv_toolchains/cygwin-rv23/bin');binary=folder/'sail_act4_reference.exe'
report=dict(passed=False,scope='ACT4 host ELF/signature driver over the genuine Sail 0.13.1 library; not a DUT verdict',
    model_commit=library['commit'],library_report='out/act4/sail-0.13.1/library_report.json',
    library_report_sha256=sha(folder/'library_report.json'),generator_sha256=sha(__file__),
    driver_inputs={p:sha(ROOT/p) for p in ['scripts/reference/act4_sail_driver.cpp','scripts/reference/sail_trace_callbacks.h']})
with Simulator() as sim:
    sim.env['PATH']=str(cygwin)+';'+os.environ['PATH']
    include=[src+'/c_emulator',src+'/dependencies/elfio',build,build+'/c_emulator',build+'/config',
             build+'/_deps/jsoncons-src/include',prefix+'/scripts/reference',
             '/cygdrive/c/rv_toolchains/sail-0.20.3/sail/share/sail/lib']
    report['compile'],_=sim.run([cygwin/'g++.exe','-std=gnu++17','-O1',*['-I'+p for p in include],
        prefix+'/scripts/reference/act4_sail_driver.cpp',src+'/c_emulator/riscv_callbacks_log.cpp',
        build+'/c_emulator/libriscv_model.a',build+'/dependencies/softfloat/libsoftfloat.a',
        build+'/sail_runtime/libsail_runtime.a','-lgmp','-o',prefix+'/out/act4/sail-0.13.1/'+binary.name],folder/'driver_compile.log',180)
    report['version'],output=sim.run([binary,'--version'],folder/'driver_version.log',30)
    assert output.strip()=='0.13.1',output
    report.update(passed=True,binary=binary.relative_to(ROOT).as_posix(),binary_sha256=sha(binary))
dump(folder/'driver_report.json',report)
print('PASS genuine Sail 0.13.1 signature driver for ACT4',flush=True)

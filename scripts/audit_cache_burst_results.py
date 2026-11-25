"""Bind the burst implementation's completed results to sources and raw runs."""
import argparse,hashlib,json,re,subprocess
from sim_runner import ROOT,source_inputs,sha,dump

parser=argparse.ArgumentParser()
parser.add_argument('--require-coremark',action='store_true')
args=parser.parse_args()
def read(name):return json.loads((ROOT/name).read_bytes())
def run_check(run):
    assert run['passed'] and run['exit_code']==0
    assert sha(ROOT/run['log'])==run['log_sha256']
def model_check(model):
    assert model['inputs']==source_inputs(model['inputs'])
    assert sha(ROOT/model['binary'])==model['binary_sha256']

native=read('out/rva23/hypervisor_integration/report.json')
assert native['passed'];model_check(native['model']);run_check(native['run'])
assert native['runtime_inputs']==source_inputs(native['runtime_inputs'])
assert native['source_sha256']==sha(ROOT/'sw/tests/rv64_hypervisor_basic.S')
assert native['elf_sha256']==sha(ROOT/'out/rva23/hypervisor_integration/test.elf')
assert native['trace_sha256']==sha(ROOT/'out/rva23/hypervisor_integration/commit.csv')
before=read('out/performance/cache_burst_before/model.json');after=native['model']
changes={p for p in set(before['inputs'])|set(after['inputs'])
         if before['inputs'].get(p)!=after['inputs'].get(p)}
assert changes=={'rtl/soc/rv23_cache.sv','rtl/soc/rv_local_to_axi_bridge.sv','rtl/soc/rv23_soc_top.sv'}
assert before['params']==after['params']
assert sha(ROOT/before['binary'])==before['binary_sha256']
# Bind the captured measured baseline to the stated pre-change Git tree too.
for name,digest in before['inputs'].items():
    content=subprocess.check_output(['git','show','7e9388b:'+name],cwd=ROOT)
    assert hashlib.sha256(content).hexdigest()==digest,name

directed={}
for name in ['unit','sram']:
    path=f'out/performance/cache_burst/{name}.json';report=read(path);assert report['passed']
    for model in report['results']:
        assert model['passed'];model_check(model);run_check(model['run'])
    a,b=report['results'];assert b['cold_cycles']<a['cold_cycles']
    directed[name]=dict(report_sha256=sha(ROOT/path),scope=report['scope'],
        before_cycles=a['cold_cycles'],after_cycles=b['cold_cycles'],
        cycle_reduction_percent=100*(a['cold_cycles']-b['cold_cycles'])/a['cold_cycles'],
        results=report['results'])

path='out/rva23/vector_word_irq/report.json';irq=read(path)
assert irq['passed'] and len(irq['cases'])==12;model_check(irq['model'])
assert irq['runtime_inputs']==source_inputs(irq['runtime_inputs'])
for case in irq['cases']:
    run_check(case['run'])
    folder=(ROOT/case['run']['log']).parent
    assert sha(folder/'test.elf')==case['elf_sha256']
    assert sha(folder/'commit.csv')==case['trace_sha256']
    c=case['counts'];assert c['last_rf']<c['retire']<c['trap'] and c['scalar']>c['retire']
    expected_refills=(1 if case['short_vl'] else 2) if case['cold'] else 0
    assert c['refills']==expected_refills

coremark={}
for n in [2,10]:
    path=f'out/performance/cache_burst/coremark_{n}.json';report=read(path)
    if not report['passed']:
        assert not args.require_coremark,f'CoreMark {n} is still pending'
        coremark[str(n)]={'complete':False};continue
    model_check(report['model']);run_check(report['run']);run_check(report['before']['run'])
    assert report['model']['inputs']==native['model']['inputs']
    assert report['model']['binary_sha256']==native['model']['binary_sha256']
    elf=ROOT/f'out/performance/rv64_coremark/o3_rvv_{n}/coremark.elf'
    assert sha(elf)==report['elf_sha256']==report['before']['elf_sha256']
    values=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]',(ROOT/report['run']['log']).read_text())]
    packet=values[values.index(0x434d0001):][:12]
    assert packet==report['packet'] and packet[1]==n and packet[6:10]==[0xe9f5,0xe714,0x1fd7,0x8e3a]
    assert report['instructions']==report['before']['instructions']
    coremark[str(n)]=dict(complete=True,report_sha256=sha(ROOT/path),elf_sha256=report['elf_sha256'],
        before_cycles=report['before']['cycles'],after_cycles=report['cycles'],instructions=report['instructions'],
        ipc=report['ipc'],cycle_reduction_percent=report['cycle_reduction_percent'],
        coremark_per_mhz_estimate=report['coremark_per_mhz_estimate'],packet=packet,run=report['run'])

dump(ROOT/'docs/evidence/cache_burst_refill.json',dict(passed=True,complete_profile_validation=False,
    physical_timing_validated=False,burst_linux_complete=False,before_commit='7e9388b',
    scope='Streaming AXI refill: directed transport/cache/SRAM and native H/V/PLIC IRQ boundaries; CoreMark completion flags are explicit. Not full ACT/RV32 release or Linux boot sign-off.',
    driver_sha256=sha(__file__),native_inputs=native['model']['inputs'],native_model=native['model'],
    native_functional_run=native['run'],directed=directed,irq=irq,coremark=coremark))
print('PASS source-bound cache burst audit; CoreMark completion', {n:r['complete'] for n,r in coremark.items()},flush=True)

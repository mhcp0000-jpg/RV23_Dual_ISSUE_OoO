"""Replay saved self-checking scalar profile ELFs on the same full H/V SoC.

No ELF is rebuilt. The original arithmetic oracles are embedded in the
programs. Native host packets and precise fault streams must also match.
"""
import concurrent.futures,csv,json,re
from sim_runner import ROOT,Simulator,sha,dump,source_inputs

folder=ROOT/'out/rva23/profile_hypervisor_replay';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
assert '-GHAS_H=1' in model['params'] and '-GHAS_V=1' in model['params'] and '-GXLEN=64' in model['params']
files=(ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv','tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
inputs=source_inputs(files);assert inputs==model['inputs']
runtime={p:sha(ROOT/p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex','sw/benchmarks/coremark/rv32_tim.ld']}
cases=[]
def elf_hashes(node):
    values=[]
    if isinstance(node,dict):
        for key,value in node.items():
            if key=='elf_sha256':values.append(value)
            else:values.extend(elf_hashes(value))
    elif isinstance(node,list):
        for value in node:values.extend(elf_hashes(value))
    return values
def add(name,report_path,elf_path,trace_path,log_path):
    report=json.loads((ROOT/report_path).read_text(encoding='utf-8'));assert report['passed'],name
    assert report.get('model_inputs',report.get('model',{}).get('inputs'))==inputs,name
    assert sha(ROOT/elf_path) in elf_hashes(report),name
    cases.append(dict(name=name,original_report=report_path,original_report_sha256=sha(ROOT/report_path),
                      elf=elf_path,elf_sha256=sha(ROOT/elf_path),baseline_trace=trace_path,
                      baseline_trace_sha256=sha(ROOT/trace_path),baseline_log=log_path,baseline_log_sha256=sha(ROOT/log_path)))

r=json.loads((ROOT/'out/rva23/scalar/report.json').read_text(encoding='utf-8'))
add('scalar/bitmanip','out/rva23/scalar/report.json',r['elf'],'out/rva23/scalar/commit.csv','out/rva23/scalar/simulation.log')
add('scalar/supervisor','out/rva23/scalar/report.json',r['supervisor']['elf'],
    'out/rva23/scalar/supervisor_commit.csv','out/rva23/scalar/supervisor_simulation.log')
for name in ['sv39','svinval','atomic','atomic_sv39','cbo','cbo_sv39','fp_state','fp_sv39','misaligned','misaligned_sv39']:
    base='out/rva23/'+name
    add(name,base+'/report.json',base+'/test.elf',base+'/commit.csv',base+'/simulation.log')
for name,labels in [('profile_scalar',['instructions','wait']),('pointer_mask',['bare','sv39'])]:
    base='out/rva23/'+name
    for label in labels:add(name+'/'+label,base+'/report.json',base+'/'+label+'.elf',
                            base+'/'+label+'_commit.csv',base+'/'+label+'_simulation.log')
for batch in range(9):
    base='out/rva23/fp_integration'
    add('fp_integration/'+str(batch),base+'/report.json',base+f'/batch_{batch}.elf',
        base+f'/batch_{batch}.csv',base+f'/simulation_{batch}.log')

def fresh():
    for p,h in {**inputs,**runtime}.items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
    for case in cases:
        for key in ['original_report','elf','baseline_trace','baseline_log']:
            assert sha(ROOT/case[key])==case[key+'_sha256'],case[key]
def traps(path):
    with path.open(newline='') as stream:
        return [{k:row[k] for k in ['pc','instruction','cause','tval']} for row in csv.DictReader(stream)
                if row['trap']=='1' and int(row['pc'],16)>=0x40000000]
def packets(text):return re.findall(r'\[host-event kind=0 data=0x([0-9a-fA-F]{8})\]',text)

fresh();report=dict(passed=False,scope='Saved self-checking scalar profile ELFs replayed without rebuilding on the same full H/V-enabled RV64 SoC; not full architectural certification',
                    model=model,runtime_inputs=runtime,generator_sha256=sha(__file__),cases=[])
path=folder/'report.json';dump(path,report)
with Simulator() as sim:
    def replay(case):
        dest=folder/case['name'];dest.mkdir(parents=True,exist_ok=True);trace=dest/'commit.csv'
        run,text=sim.run([ROOT/model['binary'],f'+elf={case["elf"]}',f'+trace_file={trace.relative_to(ROOT).as_posix()}',
            '+quiet_commit','+timeout_cycles=4000000','+expected_exit_code=0'],dest/'simulation.log',240)
        assert 'PASS rv32_program_tb' in text and 'ELF AXI readback PASS total=' in text,case['name']
        assert packets(text)==packets((ROOT/case['baseline_log']).read_text(encoding='utf-8')),case['name']
        expected=traps(ROOT/case['baseline_trace']);actual=traps(trace)
        assert actual==expected,(case['name'],actual,expected)
        return {**case,'passed':True,'run':run,'trace':trace.relative_to(ROOT).as_posix(),
                'trace_sha256':sha(trace),'traps':actual}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        pending={pool.submit(replay,case):case['name'] for case in cases}
        for future in concurrent.futures.as_completed(pending):
            result=future.result();report['cases'].append(result);dump(path,report)
            print('PASS saved ELF on H/V SoC',result['name'],flush=True)
fresh();report['cases'].sort(key=lambda row:row['name']);report['passed']=True;dump(path,report)
print(f'PASS same-ELF H/V replay {len(cases)} programs including all 5261 scalar FP oracle cases',flush=True)

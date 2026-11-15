"""Exact-ELF comparison of serialized and banked caches, plus retire-gap evidence.

The old executable, source tree, reports and both iteration ELF files are
preserved under banked_before. No old-project timing/build job is resumed.
"""
import csv,itertools,json,re,subprocess
from sim_runner import ROOT,Simulator,GCC,sha,dump

before=ROOT/'out/performance/banked_before'
output=ROOT/'out/performance/banked_after';output.mkdir(parents=True,exist_ok=True)
old_model=json.loads((before/'out/programs/model.json').read_text())
new_model=json.loads((ROOT/'out/programs/model.json').read_text())
old_report=json.loads((before/'out/programs/report.json').read_text())
old_case=next(c for c in old_report['cases'] if c['name']=='coremark')
long_report=json.loads((before/'out/performance/iterations/report.json').read_text())
long_case=next(c for c in long_report['cases'] if c['iterations']==10)
def fresh():
    for model,base in [(old_model,before),(new_model,ROOT)]:
        for path,digest in model['inputs'].items():assert sha(base/path)==digest,path
        assert sha(base/model['binary'])==model['binary_sha256']
    rom=old_report['runtime_inputs']
    assert sha(ROOT/rom['bootrom_file'])==rom['bootrom_sha256']
fresh()
def parse(text):
    assert 'ELF AXI readback PASS' in text and 'PASS rv32_program_tb' in text
    values=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([0-9a-fA-F]{8})\]',text)]
    start=values.index(0x434d0001);packet=values[start:start+12]
    assert len(packet)==12 and packet[6:10]==[0xe9f5,0xe714,0x1fd7,0x8e3a] and packet[11]&0x17==1
    cycles=packet[2]+(packet[3]<<32);instructions=packet[4]+(packet[5]<<32)
    counters=re.search(r'CACHE_PERF (.*)',text);assert counters
    path=re.search(r'PATH_PERF (.*)',text)
    return {'iterations':packet[1],'packet':packet,'cycles':cycles,'instructions':instructions,
        'ipc':instructions/cycles,'whole_program_cache':{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',counters[1])},
        'whole_program_path':{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',path[1])} if path else None}
def gaps(file,elf):
    symbols=subprocess.check_output([str(GCC/'riscv-none-elf-nm.exe'),str(elf)],text=True)
    def address(name):return int(next(x.split()[0] for x in symbols.splitlines() if x.endswith(' '+name)),16)
    start,stop=address('start_time'),address('stop_time')
    active=False;first=None;previous=None;count=0;one=0;two=0;pcs={}
    with file.open(newline='') as stream:
        for cycle,group in itertools.groupby(csv.DictReader(stream),lambda r:int(r['cycle'])):
            rows=list(group)
            if not active and any(int(r['pc'],16)==start for r in rows):active=True;first=cycle
            if not active:continue
            gap=0 if previous is None else max(0,cycle-previous-1)
            row=rows[0];key=row['pc']
            item=pcs.setdefault(key,{'pc':key,'instruction':row['instruction'],'mnemonic':row['mnemonic'],
                                    'gap_cycles':0,'following_groups':0,'max_gap':0})
            item['gap_cycles']+=gap;item['following_groups']+=1;item['max_gap']=max(item['max_gap'],gap)
            if any(int(r['pc'],16)==stop for r in rows):
                duration=cycle-first
                assert duration-(one+two)==sum(v['gap_cycles'] for v in pcs.values())
                return {'scope':'Retire cycle groups from start_time entry to stop_time entry; differs from CSR bookends. Gap charged to following PC, not causal attribution.',
                    'cycles':duration,'instructions':count,'single_commit_cycles':one,'dual_commit_cycles':two,
                    'no_commit_cycles':duration-one-two,'top_following_pcs':sorted(pcs.values(),key=lambda x:-x['gap_cycles'])[:16]}
            count+=len(rows);one+=len(rows)==1;two+=len(rows)==2;previous=cycle
    raise RuntimeError('Missing profiling function entries')

result={'passed':False,'state':'running','cases':[],
    'scope':'Same saved ELF bytes on both executables; main AXI64, I/D 32KiB, SRAM1MiB unchanged'}
report_path=output/'report.json'
previous=json.loads(report_path.read_text()) if report_path.exists() else {}
previous_cases={c['iterations']:c for c in previous.get('cases',[]) if c.get('passed')}
dump(report_path,result)
with Simulator() as sim:
    for iterations,baseline,elf in [
        (2,old_case['coremark'],before/'out/programs/coremark/test.elf'),
        (10,long_case,before/'out/performance/iterations/iter_10/test.elf')]:
        digest=sha(elf)
        assert digest==(old_case['program']['elf_sha256'] if iterations==2 else long_case['elf_sha256'])
        records={}
        for label,model,base in [('before',old_model,before),('after',new_model,ROOT)]:
            cached=previous_cases.get(iterations)
            if label=='after' and cached and (iterations!=2 or 'control_stream' in cached) and previous.get('after_model_inputs')==new_model['inputs'] and \
               previous.get('after_binary_sha256')==new_model['binary_sha256'] and cached['elf_sha256']==digest and \
               sha(ROOT/cached['after']['run']['log'])==cached['after']['run']['log_sha256']:
                if iterations==2:
                    assert sha(output/'after_2/commit.csv')==cached['control_stream']['after_trace_sha256']
                records[label]=cached['after'];print('REUSE bound after baseline',iterations,flush=True);continue
            if label=='before' and iterations==2 and cached and 'control_stream' in cached and \
               previous.get('before_binary_sha256')==old_model['binary_sha256'] and \
               cached['elf_sha256']==digest and \
               sha(ROOT/cached['before']['run']['log'])==cached['before']['run']['log_sha256']:
                assert sha(output/'before_2/commit.csv')==cached['control_stream']['before_trace_sha256']
                records[label]=cached['before'];print('REUSE bound before-2 baseline',flush=True);continue
            if label=='before' and iterations==10:
                log=before/'out/performance/iterations/iter_10/simulation.log'
                assert sha(log)==long_case['run']['log_sha256']
                records[label]=parse(log.read_text());records[label]['run']=long_case['run'];continue
            folder=output/f'{label}_{iterations}';folder.mkdir(exist_ok=True)
            trace=(folder/'commit.csv').relative_to(ROOT).as_posix() if iterations==2 else 'NUL'
            print('RUN exact ELF',label,'iterations',iterations,flush=True)
            run,text=sim.run([base/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
                f'+trace_file={trace}','+quiet_commit',f'+timeout_cycles={iterations*10000000}',
                '+expected_exit_code=0'],folder/'simulation.log',max(600,iterations*90))
            fresh();assert sha(elf)==digest
            records[label]=parse(text);records[label]['run']=run
            if iterations==2:records[label]['retire_gaps']=gaps(ROOT/trace,elf)
        assert records['before']['cycles']==baseline['cycles']
        assert records['before']['instructions']==records['after']['instructions']
        assert records['after']['cycles']<records['before']['cycles']
        case={'iterations':iterations,'passed':True,'elf':elf.relative_to(ROOT).as_posix(),
            'elf_sha256':digest,**records,
            'speedup':records['before']['cycles']/records['after']['cycles']}
        result['cases'].append(case);dump(report_path,result)
        print('PASS exact ELF iterations',iterations,'IPC',records['before']['ipc'],'->',records['after']['ipc'],flush=True)
result.update(passed=True,state='finished',before_binary_sha256=old_model['binary_sha256'],
    before_source_root='out/performance/banked_before',
    before_model='out/performance/banked_before/out/programs/model.json',
    after_binary_sha256=new_model['binary_sha256'],after_model_inputs=new_model['inputs'])
dump(report_path,result)
print('PASS banked performance and retire-gap comparison',flush=True)

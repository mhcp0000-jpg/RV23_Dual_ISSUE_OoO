"""Fail closed unless every RV32 target and regression gate has current evidence."""
from pathlib import Path
import csv,json,re,sys
from sim_runner import ROOT,sha,dump

def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8-sig'))
def require(condition,message):
    if not condition:raise RuntimeError(message)
def fresh(inputs):
    for file,digest in inputs.items():require(sha(ROOT/file)==digest,'Changed input: '+file)
def native(run):
    require(run['passed'],'Native run not passed')
    require(sha(ROOT/run['log'])==run['log_sha256'],'Changed native log: '+run['log'])
    if run.get('expected_failure'):require(run['exit_code']!=0,'Negative control did not fail')
    else:require(run['exit_code']==0,'Native exit not zero')
def model(record):
    fresh(record['inputs'])
    require(sha(ROOT/record['binary'])==record['binary_sha256'],'Changed simulator executable')
    native(record['compile']);native(record['build'])
gates=[]
try:
    top=(ROOT/'rtl/soc/rv23_soc_top.sv').read_text()
    require(re.search(r'parameter int unsigned XLEN\s*=\s*32\b',top),'Primary top is not RV32')
    pkg=(ROOT/'rtl/soc/rv23_pkg.sv').read_text()
    for name,value in [('SRAM_KB',1024),('ICACHE_KB',32),('DCACHE_KB',32),('CACHE_LINE_BYTES',64)]:
        require(re.search(rf'\b{name}\s*=\s*{value}\b',pkg),'Wrong hardware geometry: '+name)
    gates.append({'gate':'RV32 default and requested memory/cache geometry','passed':True})
    sources=(ROOT/'rtl/filelist.f').read_text().splitlines()
    require(sources==(ROOT/'sim/sources.f').read_text().splitlines(),'Different source lists')
    source_manifest=read('docs/source_manifest.json')
    fresh({x['path']:x['sha256'] for x in source_manifest['files']})
    require(set(sources)=={x['path'] for x in source_manifest['files']},'Manifest/source set mismatch')
    base=read('out/verification.json');extended=read('out/extended.json')
    require(base['passed'] and extended['passed'],'RV32 baseline or random tests incomplete')
    fresh(base['source_sha256'])
    for item in base['results']:
        require(sha(ROOT/('tb/'+item['top']+'.sv'))==item['test_sha256'],'Changed baseline TB')
        require(sha(ROOT/('out/'+item['top']+'/V'+item['top']+'.exe'))==item['binary_sha256'],'Changed baseline binary')
    require({r['top'] for r in base['results']}=={'rv23_boot_tb','rv23_memory_tb','rv23_cache_fault_tb'},'Missing baseline test')
    cache_log=(ROOT/'out/rv23_cache_fault_tb_simulation.log').read_text()
    require('CACHE CAPACITY PASS lines=512 bytes=32768' in cache_log,'Missing 512-line capacity verification')
    require('SNOOP RACES PASS' in cache_log,'Missing snoop/refill/hit/response races')
    require('SYSTEM SNOOP PASS' in (ROOT/'out/rv23_memory_tb_simulation.log').read_text(),
            'Missing CPU/debug snoop integration checks')
    system_log=(ROOT/'out/rv23_memory_tb_simulation.log').read_text()
    require('BANKED HIT PASS I128=1cycle D64=1cycle' in system_log,'Missing bank bandwidth/latency verification')
    require('I PAIR RACES PASS' in system_log,'Missing paired-fetch coherence races')
    require('BANK WRITE COLLISION PASS' in cache_log,'Missing snoop/refill bank write collision')
    require('CACHE LAUNCH PASS' in cache_log,'Missing fall-through timing/completion/hold checks')
    require('WRITE RESPONSE OWNERSHIP PASS' in system_log,'Missing held write response ownership')
    launch_control=read('out/cache_launch_negative.json');model(launch_control);native(launch_control['run'])
    coarse_lock=read('out/cache_word_lock_negative.json');model(coarse_lock);native(coarse_lock['run'])
    require(len(extended['seeds'])==3,'Missing random seeds')
    for item in extended['seeds']:
        native(item['run'])
        require(sha(ROOT/'tb/rv23_memory_tb.sv')==item['test_sha256'],'Stale random test')
        require(sha(ROOT/'out/rv23_memory_tb/Vrv23_memory_tb.exe')==item['binary_sha256'],'Stale random simulator')
    gates.append({'gate':'Current RV32 boot, memory, cache faults/capacity and 3072 seeded transactions','passed':True})
    regression=read('out/regression/report.json');spec=read('config/regression.json')
    require(regression['passed'] and regression['state']=='finished','Original regressions incomplete')
    require({x['name'] for x in regression['cases']}=={x['name'] for x in spec['cases']},'Regression case set differs')
    for case in regression['cases']:
        require(case['passed'],'Failed original case '+case['name']);model(case)
        for run in case['runs']:native(run)
    fp=next(x for x in regression['cases'] if x['name']=='rv_fpu_diff_tb')
    require(sha(ROOT/'out/regression/fpu_vectors.hex')==fp['vector_sha256'],'Changed FP oracle vectors')
    require(len(fp['runs'])==2 and all('113600' in ' '.join(r['witnesses']) for r in fp['runs']),'FP corpus/rm coverage missing')
    native(fp['oracle_negative_control'])
    pressure=next(c for c in regression['cases'] if c['name']=='rv_backend_seq_admission_tb')
    require('epochs=3' in ' '.join(pressure['runs'][0]['witnesses']),'Missing sequence-pressure coverage')
    negative=read('out/sequence_credit_negative.json');model(negative);native(negative['run'])
    require('count=22 span=127 requested=2' in (ROOT/negative['run']['log']).read_text(),
            'Prior sequence-allocation failure not independently reproduced')
    gates.append({'gate':'58 block/backend cases including ROB sequence pressure, 113600 static + 113600 dynamic FP vectors and negative controls','passed':True})
    bus=read('out/bus_lock_report.json');require(bus['passed'] and len(bus['cases'])==2,'AXI stall verification missing')
    for record in bus['cases']:model(record);native(record['run'])
    require(bus['cases'][1]['run']['exit_code']!=0,'Pre-fix AXI bug was not detected')
    gates.append({'gate':'AXI AR/AW stall lock and pre-fix failure reproduction','passed':True})
    programs=read('out/programs/report.json');program_spec=read('out/programs/inputs.json')
    require(programs['passed'] and programs['state']=='finished','Software regressions incomplete')
    require({c['name'] for c in programs['cases']}=={c['name'] for c in program_spec['cases']},'Software case set differs')
    fresh(programs['model_inputs']);model(read('out/programs/model.json'))
    # Runtime ROM images and program ELF objects are also part of the contract.
    rom=ROOT/'tb/fixtures/bootrom/bootrom_host_jump.hex'
    require(sha(rom)==read('out/programs/runtime_inputs.json')['bootrom_sha256'],'Changed boot ROM')
    require(programs['runtime_inputs']==read('out/programs/runtime_inputs.json'),'Program runtime image binding differs')
    for case in programs['cases']:
        require(case['passed'],'Failed program '+case['name']);native(case['run'])
        fresh(case['program']['inputs'])
        require(sha(ROOT/case['program']['elf'])==case['program']['elf_sha256'],'Changed ELF')
        require((ROOT/case['program']['elf']).read_bytes()[:6]==b'\x7fELF\x01\x01','Software is not ELF32 little-endian')
    system=next(c for c in programs['cases'] if c['name']=='system_contract')
    require([int(t['cause']) for t in system['stats']['traps']]==[2,2,2,3,7,11],'RV32 illegal/IRQ trace coverage differs')
    require([t['instruction'] for t in system['stats']['traps'][:3]]==['00003283','00003023','0000029b'],'RV64-only instructions not checked')
    trace=ROOT/'out/programs/system_contract/commit.csv'
    with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
    require(any(r['mnemonic']=='FENCE.I' for r in rows),'Missing actual FENCE.I retirement')
    values={int(r['wdata'],16) for r in rows if r['rd']=='10' and r['rd_write']=='1'}
    require({1,42}<=values,'Self-modified instruction did not produce both expected results')
    cm=next(c['coremark'] for c in programs['cases'] if c['name']=='coremark')
    require(cm['packet'][6:10]==[0xe9f5,0xe714,0x1fd7,0x8e3a],'CoreMark CRC mismatch')
    require(cm['cycles']>0 and cm['instructions']>0 and cm['certified_score'] is False,'Invalid CoreMark classification')
    gates.append({'gate':'22 RV32 ELF cases, actual IRQ/SMC/debug, PMP warm/fence, negative software controls, CoreMark CRC','passed':True})
    perf=read('out/performance/banked_after/report.json')
    require(perf['passed'] and perf['state']=='finished','Banked cache performance verification incomplete')
    fresh(perf['after_model_inputs'])
    current_model=read('out/programs/model.json')
    require(current_model['binary_sha256']==perf['after_binary_sha256'],'Stale banked performance model')
    old_model=read(perf['before_model']);prefix=perf['before_source_root']+'/'
    fresh({prefix+p:d for p,d in old_model['inputs'].items()})
    require(sha(ROOT/(prefix+old_model['binary']))==perf['before_binary_sha256'],'Changed baseline model')
    require({c['iterations'] for c in perf['cases']}=={2,10},'Missing iteration comparison')
    for item in perf['cases']:
        require(item['passed'] and sha(ROOT/item['elf'])==item['elf_sha256'],'Changed comparison ELF')
        for side in ['before','after']:native(item[side]['run'])
        require(item['after']['instructions']==item['before']['instructions'],'Different timed instruction count')
        require(item['after']['cycles']<item['before']['cycles'],'No measured cache speedup')
        require(item['after']['packet'][6:10]==item['before']['packet'][6:10],'Different benchmark CRC')
    control=next(c for c in perf['cases'] if c['iterations']==2)['control_stream']
    require(control['passed'] and control['instructions']>500000,'Timed-body control trace not checked')
    for side in ['before','after']:
        require(sha(ROOT/control[side+'_trace'])==control[side+'_trace_sha256'],'Changed comparison trace')
    wt=read('out/performance/write_path/report.json')
    require(wt['passed'] and wt['current_report_sha256']==sha(ROOT/'out/performance/banked_after/report.json'),
            'Stale write-path performance comparison')
    require(wt['baseline_report_sha256']==sha(ROOT/wt['baseline_report']),'Changed write-path baseline report')
    fresh(wt['before_model_inputs'])
    require(sha(ROOT/wt['before_binary'])==wt['before_binary_sha256'],'Changed write-path baseline simulator')
    for c in wt['cases']:native(c['before_run'])
    fresh(wt['after_model_inputs'])
    require(wt['after_binary_sha256']==current_model['binary_sha256'],'Stale write-path simulator')
    require({c['iterations'] for c in wt['cases']}=={2,10} and
            all(c['after_cycles']<c['before_cycles'] for c in wt['cases']),'Write-path improvement missing')
    gates.append({'gate':'Exact-ELF 2/10-iteration cache cycle recovery and identical timed-body retirement metadata','passed':True})
    result={'passed':True,'target':'RV32IMFC_Zicsr_Zifencei / ilp32f','gates':gates,
        'source_sha256':base['source_sha256'],'coremark':cm,
        'cache_performance':[{'iterations':c['iterations'],'speedup':c['speedup'],
            'before_ipc':c['before']['ipc'],'after_ipc':c['after']['ipc']} for c in perf['cases']],
        'limits':['Not full ISA certification/long differential','No standard JTAG Debug Module',
                  'No Linux/MMU/S-mode/A/D/V','No timing/STA or historical IPC claim']}
except Exception as error:
    result={'passed':False,'completed_gates':gates,'failure':str(error)}
dump(ROOT/'out/rv32_release_audit.json',result)
print(json.dumps(result if not result['passed'] else {'passed':True,'gates':len(gates),'coremark':cm},indent=2))
sys.exit(not result['passed'])

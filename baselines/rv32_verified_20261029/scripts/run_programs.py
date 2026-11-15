"""Rebuild former RV32 payloads and run them on the cached 1 MiB SRAM SoC."""
from pathlib import Path
import argparse,csv,json,re,subprocess,sys
from sim_runner import ROOT,Simulator,GCC,sha,dump
ap=argparse.ArgumentParser()
ap.add_argument('--prepare-only',action='store_true')
ap.add_argument('--only',nargs='+')
ap.add_argument('--resume',action='store_true')
ap.add_argument('--bus-debug',action='store_true')
args=ap.parse_args()
OUTPUT=ROOT/'out/programs';OUTPUT.mkdir(parents=True,exist_ok=True)
cases=[]
with Simulator() as sim:
    runtime_inputs={'bootrom_file':'tb/fixtures/bootrom/bootrom_host_jump.hex',
        'bootrom_sha256':sha(ROOT/'tb/fixtures/bootrom/bootrom_host_jump.hex')}
    dump(OUTPUT/'runtime_inputs.json',runtime_inputs)
    cc=GCC/'riscv-none-elf-gcc.exe'
    common=['-march=rv32imfc_zicsr_zifencei','-mabi=ilp32f','-mcmodel=medany',
        '-msmall-data-limit=0','-O1','-ffreestanding','-fno-builtin','-fno-common',
        '-fno-asynchronous-unwind-tables','-fno-unwind-tables','-nostdlib','-nostartfiles',
        '-Wl,--build-id=none','-Wl,--no-relax']
    linker='sw/tests/rv32_c_loop/rv32_tim.ld'
    htif_linker='sw/tests/htif_smoke/rv32_htif.ld'
    def build(name,files,flags=(),link=None,htif=False,expected_exit=0,markers=(),
              debug=False,negative=False,traps=None):
        folder=OUTPUT/name;folder.mkdir(exist_ok=True)
        elf=folder/'test.elf';selected_link=link or linker
        sim.run([cc,*common,*flags,*files,'-T',selected_link,'-lgcc','-o',elf],folder/'compile.log',60)
        case={'name':name,'elf':elf.relative_to(ROOT).as_posix(),'elf_sha256':sha(elf),
            'compiler_args':common+list(flags)+list(files)+['-T',selected_link,'-lgcc'],
            'inputs':{p:sha(ROOT/p) for p in [*files,selected_link]},'htif':htif,
            'expected_exit':expected_exit,'markers':list(markers),'debug':debug,
            'negative':negative,'payload_traps':traps}
        cases.append(case)
    build('c_loop',['sw/tests/rv32_c_loop/rv32_start.S','sw/tests/rv32_c_loop/rv32_loop_smoke.c'],
          ['-fno-unroll-loops'],markers=['009e00b9'],traps=0)
    build('system_contract',['sw/tests/rv32_system_contract.S'],markers=['52563332'],debug=True,traps=6)
    for name,file,htif in [
        ('external_access_fault','sw/tests/external_access_fault/external_access_fault.S',True),
        ('precise_faults','sw/tests/lsu_validation_pipeline/precise_faults.S',False),
        ('dual_lsu_pressure','sw/tests/lsq_capacity_rotation/dual_lsu_pressure.S',False),
        ('older_store_fault','sw/tests/lsq_capacity_rotation/older_store_fault.S',False),
        ('csr_trace','sw/tests/pmp_fetch/csr_trace.S',True),
        ('pmp_parcel_boundary','sw/tests/pmp_fetch/parcel_boundary.S',True),
        ('htif_smoke','sw/tests/htif_smoke/htif_smoke.S',True),
        ('dv_arithmetic','sw/imported/dv_arithmetic_smoke/test.S',True)]:
        if not (ROOT/file).exists():
            if name=='htif_smoke':
                available=list((ROOT/'sw/tests/htif_smoke').glob('*.S'))
                if len(available)==1:file=available[0].relative_to(ROOT).as_posix()
            if not (ROOT/file).exists():raise RuntimeError('Missing required software input: '+file)
        build(name,[file],link=htif_linker if htif else linker,htif=htif)
    for warm in [0,1]:
        for flush in [0,1]:
            build(f'pmp_protection_w{warm}_f{flush}',['sw/tests/pmp_fetch/protection_change.S'],
                [f'-DWARM={warm}',f'-DFLUSH={flush}'],link=htif_linker,htif=True,expected_exit=1,traps=1)
    build('older_store_fault_negative',['sw/tests/lsq_capacity_rotation/older_store_fault.S'],
          ['-DLSQ_FAULT_EXPECTED_CAUSE=7'],negative=True)
    build('dual_lsu_pressure_negative',['sw/tests/lsq_capacity_rotation/dual_lsu_pressure.S'],
          ['-DLSQ_PRESSURE_WRONG_EXPECTED=1'],negative=True)
    # Generate/rebuild the former exact FCVT corpus, including a wrong-answer control.
    for negative in [False,True]:
        name='fp_conversion'+('_negative' if negative else '')
        folder=OUTPUT/name;folder.mkdir(exist_ok=True)
        oracle=folder/('oracle_'+sha(ROOT/'sw/tests/fp_conversion_vectors/gen_vectors.py')[:12])
        if not oracle.exists():
            sim.run([sys.executable,'sw/tests/fp_conversion_vectors/gen_vectors.py',
                '--output',oracle],folder/'generate.log',60)
        corpus=json.loads((oracle/'vectors.json').read_text())
        assert corpus['headerSha256'].lower()==sha(oracle/'vectors.h')
        build(name,['sw/tests/fp_conversion_vectors/start.S','sw/tests/fp_conversion_vectors/test.c'],
              ['-O2','-I'+oracle.relative_to(ROOT).as_posix(),
               *(['-DFP_CONVERSION_WRONG_EXPECTED=1'] if negative else [])],
              markers=[] if negative else ['46504356'],negative=negative)
        cases[-1]['oracle_sha256']=sha(oracle/'vectors.h')
    # The original small ELF builders remain independent opcode/ABI tests.
    for stem in ['rv32_smoke','rv32c_smoke','rv32_priv_smoke']:
        folder=OUTPUT/stem;folder.mkdir(exist_ok=True)
        elf=folder/'test.elf'
        script='scripts/build_'+stem+'_elf.ps1'
        sim.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',script,
                 '-OutputPath',str(elf)],folder/'assemble.log',30)
        cases.append({'name':stem,'elf':elf.relative_to(ROOT).as_posix(),
            'elf_sha256':sha(elf),'inputs':{script:sha(ROOT/script)},'htif':False,
            'expected_exit':0,'markers':[],'debug':False,'negative':False,'payload_traps':None})
    # Pinned upstream source is byte-for-byte copied, with the existing port.
    base='sw/benchmarks/coremark/'
    vendor=base+'upstream/'
    provenance=json.loads((ROOT/vendor/'PROVENANCE.json').read_text())
    for file,digest in provenance['files'].items():
        assert sha(ROOT/vendor/file)==digest,'CoreMark upstream source modified'
    sources=[base+'rv32_start.S',base+'port/core_portme.c']+[
        vendor+n for n in ['core_list_join.c','core_main.c','core_matrix.c','core_state.c','core_util.c']]
    build('coremark',sources,['-O2','-I'+base+'port','-I'+vendor,
        '-DPERFORMANCE_RUN=1','-DITERATIONS=2','-DTOTAL_DATA_SIZE=2000',
        '-DMAIN_HAS_NOARGC=1','-DMEM_METHOD=MEM_STATIC','-DMULTITHREAD=1'],
        link=base+'rv32_tim.ld',markers=['434d0001'],traps=0)
    dump(OUTPUT/'inputs.json',{'target':'RV32IMFC_Zicsr_Zifencei','cases':cases})
    print('PREPARED RV32 program cases',len(cases),flush=True)
    if args.prepare_only:sys.exit(0)
    sources=(ROOT/'rtl/filelist.f').read_text().splitlines()+[
        'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
    build_path=OUTPUT/'model.json'
    model=json.loads(build_path.read_text()) if args.resume and build_path.exists() else None
    current={p:sha(ROOT/p) for p in sources}
    if not(model and model['inputs']==current and (ROOT/model['binary']).exists() and
           sha(ROOT/model['binary'])==model['binary_sha256']):
        model=sim.build('rv32_program_tb','rv32_program_tb',sources)
        dump(build_path,model)
    selected=[c for c in cases if not args.only or c['name'] in args.only]
    if not selected:raise RuntimeError('No selected program tests')
    previous_path=OUTPUT/'report.json'
    previous=json.loads(previous_path.read_text()) if args.resume and previous_path.exists() else {}
    done={c['name']:c for c in previous.get('cases',[]) if c.get('passed')}
    report={'passed':False,'state':'running','expected_cases':[c['name'] for c in selected],
            'target':'RV32IMFC_Zicsr_Zifencei','model_inputs':current,'cases':[],
            'runtime_inputs':runtime_inputs,
            'scope':'Cached SRAM SoC ELF, readback, trace and CRC; no ISA/STA certification'}
    dump(previous_path,report)
    for i,case in enumerate(selected):
        name=case['name'];folder=OUTPUT/name
        old=done.get(name)
        if old and previous.get('model_inputs')==current and old.get('program')==case and \
                previous.get('runtime_inputs')==runtime_inputs:
            report['cases'].append(old);print('REUSE bound PASS',name,flush=True);continue
        print(f'RUN PROGRAM {i+1}/{len(selected)} {name}',flush=True)
        trace=(folder/'commit.csv').relative_to(ROOT).as_posix()
        runtime=[f'+elf={case["elf"]}',f'+trace_file={trace}','+timeout_cycles=20000000',
                 '+expected_exit_code='+str(case['expected_exit']),'+quiet_commit']
        if case['htif']:runtime+=['+htif']
        if case['debug']:runtime+=['+debug_check']
        if args.bus_debug:runtime+=['+bus_debug']
        try:
            run,text=sim.run([ROOT/model['binary'],*runtime],folder/'simulation.log',600,
                'ELF reported failure exit code 1' if case['negative'] else None)
            if sha(ROOT/runtime_inputs['bootrom_file'])!=runtime_inputs['bootrom_sha256']:
                raise RuntimeError('Boot ROM changed during simulation')
            if 'ELF AXI readback PASS' not in text:raise RuntimeError('Missing AXI image/BSS readback witness')
            if not case['negative'] and 'PASS rv32_program_tb' not in text:
                raise RuntimeError('Missing final program PASS')
            for marker in case['markers']:
                if f'data=0x{marker}' not in text.lower():raise RuntimeError('Missing expected telemetry '+marker)
            stats={'payload_commits':0,'fp_writes':0,'lane1_commits':0,'traps':[]}
            with (ROOT/trace).open(newline='') as f:
                for row in csv.DictReader(f):
                    if int(row['pc'],16)<0x80000000:continue
                    stats['payload_commits']+=1
                    stats['fp_writes']+=row['rd_fp']=='1' and row['rd_write']=='1'
                    stats['lane1_commits']+=row['lane']=='1'
                    if row['trap']=='1':stats['traps'].append({k:row[k] for k in ['pc','instruction','cause','tval']})
            if not stats['payload_commits']:raise RuntimeError('No RV32 payload retired')
            if case['payload_traps'] is not None and len(stats['traps'])!=case['payload_traps']:
                raise RuntimeError('Unexpected payload trap count: '+str(stats['traps']))
            if name=='c_loop' and not(stats['fp_writes'] and stats['lane1_commits']):
                raise RuntimeError('C/FP/dual-commit coverage missing')
            if name.startswith('pmp_protection_'):
                fault=stats['traps'][0]
                if fault['cause']!='1' or int(fault['tval'],16)!=0x80000800:
                    raise RuntimeError('PMP cached authorization denial not demonstrated')
            if name=='system_contract' and 'NATIVE DEBUG PASS' not in text:
                raise RuntimeError('Native halt/debug AXI/resume test missing')
            result={'name':name,'passed':True,'program':case,'run':run,'stats':stats}
            if name=='coremark':
                values=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([0-9a-fA-F]{8})\]',text)]
                start=values.index(0x434d0001);packet=values[start:start+12]
                if len(packet)!=12 or packet[1]!=2 or packet[6:10]!=[0xe9f5,0xe714,0x1fd7,0x8e3a] or packet[11]&0x17!=1:
                    raise RuntimeError('CoreMark CRC/status failed: '+str(packet))
                cycles=packet[2]+(packet[3]<<32);instructions=packet[4]+(packet[5]<<32)
                result['coremark']={'cycles':cycles,'instructions':instructions,'ipc':instructions/cycles,
                    'iterations':2,'packet':packet,'certified_score':False,
                    'memory':'32KiB I + 32KiB D + main AXI + 1MiB SRAM'}
            print('PASS PROGRAM',name,stats['payload_commits'],flush=True)
        except Exception as error:
            result={'name':name,'passed':False,'program':case,'failure':str(error)}
            print('FAIL PROGRAM',name,str(error)[-3500:],flush=True)
        report['cases'].append(result);dump(previous_path,report)
    report['state']='finished';report['passed']=len(report['cases'])==len(selected) and all(c['passed'] for c in report['cases'])
    dump(previous_path,report)
    print('PROGRAM REGRESSION',sum(c['passed'] for c in report['cases']),'/',len(selected),flush=True)
    sys.exit(not report['passed'])

"""Interrupt a coalesced vector load on hits and misses; inspect all result bytes."""
import argparse,csv,json,re,subprocess
from sim_runner import ROOT,Simulator,GCC,sha,dump,source_inputs

parser=argparse.ArgumentParser()
parser.add_argument('--output-dir',default='out/rva23/vector_word_irq')
args=parser.parse_args()
folder=ROOT/args.output_dir;folder.mkdir(parents=True,exist_ok=True)
source='sw/tests/rv64_vector_word_irq.S';linker='scripts/reference/upstream_htif.ld'
runtime=source_inputs([source,linker,'tb/fixtures/bootrom/bootrom_host_jump64.hex'])
files=(ROOT/'rtl/filelist.f').read_text().splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/rv32_program_tb.sv','tb/rv23_vector_word_irq_tb.sv','tb/e2e/dpi/elf_loader.cpp']
cases=[]
with Simulator() as sim:
    path=folder/'model.json';model=json.loads(path.read_bytes()) if path.exists() else None
    if not model or model['inputs']!=source_inputs(files) or sha(ROOT/model['binary'])!=model['binary_sha256']:
        model=sim.build('rv23_vector_word_irq','rv23_vector_word_irq_tb',files);dump(path,model)
    for width,short,cold in [(w,s,c) for w in [8,16,32] for s in [False,True] for c in [0,1]]:
            byte_count=2*width//8 if short else 128
            target=folder/f'e{width}_cold{cold}_short{int(short)}';target.mkdir(exist_ok=True)
            elf=target/'test.elf';trace=target/'commit.csv'
            compile_run,_=sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh_zicbom','-mabi=lp64d',
                f'-DDATA_EEW={width}',f'-DTEST_COLD={cold}',f'-DTEST_ELEMENTS={2 if short else 0}','-nostdlib','-nostartfiles',
                '-Wl,--no-relax','-Wl,--build-id=none','-T',linker,source,'-o',elf],target/'compile.log',60)
            symbols=subprocess.check_output([str(GCC/'riscv-none-elf-nm.exe'),'-n',str(elf)],text=True)
            pcs={name:int(re.search(r'^([\da-f]+) \w '+name+'$',symbols,re.M)[1],16) for name in ['irq_vector','following_store']}
            digest=sha(elf)
            run,log=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
                f'+trace_file={trace.relative_to(ROOT).as_posix()}',f'+irq_pc={pcs["irq_vector"]:x}',
                f'+word_bytes={byte_count}',
                '+quiet_commit','+htif','+timeout_cycles=100000','+expected_exit_code=0'],target/'simulation.log',120)
            assert 'PASS rv32_program_tb' in log
            match=re.search(r'^WORD_IRQ (.+)$',log,re.M);assert match
            counts={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',match[1])}
            expected_reads=max(1,byte_count//8)
            assert counts['reads']==counts['responses']==counts['writes']==expected_reads
            assert counts['first']<counts['pending']<counts['last_rf']<counts['retire']<counts['trap']
            assert counts['scalar']>counts['retire'] and 0<counts['pending_reads']<=expected_reads
            assert (counts['refills']>0) if cold else counts['refills']==0
            rows=list(csv.DictReader(trace.open(newline='')))
            traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
            assert len(traps)==1 and int(traps[0]['cause'])==11
            loads=[r for r in rows if r['trap']=='0' and int(r['pc'],16)==pcs['irq_vector']]
            stores=[r for r in rows if r['trap']=='0' and int(r['pc'],16)==pcs['following_store']]
            assert len(loads)==len(stores)==1 and int(loads[0]['cycle'])<int(stores[0]['cycle'])
            assert int(loads[0]['cycle'])<int(traps[0]['cycle']) and int(traps[0]['tval'],16)==0
            assert sha(elf)==digest
            cases.append(dict(width=width,short_vl=short,bytes=byte_count,cold=bool(cold),pcs=pcs,counts=counts,compile=compile_run,
                run=run,elf_sha256=digest,trace_sha256=sha(trace)))
assert runtime==source_inputs(runtime) and model['inputs']==source_inputs(model['inputs'])
dump(folder/'report.json',dict(passed=True,complete_profile_validation=False,
    scope='Twelve native PLIC IRQ cases: EEW8/16/32, full 128-byte and two-element VL, warm/cold; all active result bytes checked in handler, final RF write before retire/trap and younger scalar-store visibility. Not all IRQ/fault races.',
    model=model,runtime_inputs=runtime,driver_sha256=sha(__file__),cases=cases))
print('PASS coalesced word-load IRQ: EEW8/16/32, full/short VL, warm/cold, all active result bytes and scalar-store ordering',flush=True)
for case in cases:print(case['width'],case['short_vl'],case['cold'],case['counts'],flush=True)

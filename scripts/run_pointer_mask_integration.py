"""Exercise Ssnpm PMM=0/7 on data, atomics, FP, MPRV and precise fault values."""
import csv,json
from sim_runner import ROOT,Simulator,GCC,sha,dump
folder=ROOT/'out/rva23/pointer_mask';folder.mkdir(parents=True,exist_ok=True)
model=json.loads((ROOT/'out/rva23/scalar/model.json').read_text())
assert '-GHAS_SSNPM=1' in model['params']
def fresh():
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
fresh()
with Simulator() as sim:
    cases=[]
    for virtual in [False,True]:
        label='sv39' if virtual else 'bare';elf=folder/(label+'.elf');trace=folder/(label+'_commit.csv')
        address=0x40003000 if virtual else 0x80070000
        bad=address|(0xff00000000000000 if virtual else 0x0100000000000000)
        cause=13 if virtual else 5;fetch_cause=12 if virtual else 1
        sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64imafc_zicsr_zifencei','-mabi=lp64f',
            '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
            f'-DVIRTUAL={int(virtual)}',f'-DDATA_ADDRESS={address}',
            f'-DTRANSFORMED_BAD_ADDRESS={bad}',f'-DFAULT_CAUSE={cause}',
            f'-DFETCH_FAULT_CAUSE={fetch_cause}',
            '-T','sw/benchmarks/coremark/rv32_tim.ld','sw/tests/rv64_pointer_mask.S','-o',elf],folder/(label+'_compile.log'),60)
        run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
            '+timeout_cycles=2000000','+expected_exit_code=0'],folder/(label+'_simulation.log'),180)
        fresh();assert 'PASS rv32_program_tb' in text and 'data=0x504d4d37' in text
        with trace.open(newline='') as stream:rows=list(csv.DictReader(stream))
        traps=[r for r in rows if r['trap']=='1' and int(r['pc'],16)>=0x80000000]
        assert [int(r['cause']) for r in traps]==[cause,4,6,cause,fetch_cause],traps
        assert [int(r['tval'],16) for r in traps]==[
            address|0xfe00000000000000,address+1,address+1,bad,0xfe00000080000000],traps
        cases.append({'label':label,'passed':True,'elf_sha256':sha(elf),'trace_sha256':sha(trace),
            'run':run,'traps':traps})
        print('PASS Ssnpm integrated',label,'MPRV/MXR/LSU/FP/A/transformed tval/unmasked fetch',flush=True)
    dump(folder/'report.json',{'passed':True,'model_inputs':model['inputs'],
        'binary_sha256':model['binary_sha256'],'source_sha256':sha(ROOT/'sw/tests/rv64_pointer_mask.S'),'cases':cases})

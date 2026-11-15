"""Observe every vector-register bit via whole stores and scalar loads on Sail/RTL.

Five checkpoints for each legal SEW/LMUL pair use tail/mask undisturbed policy,
so every stored bit has a defined exact reference value. This adds state
comparison to existing broader ACT and directed vector instruction coverage.
"""
import argparse
import concurrent.futures
import csv
import json
import os
import subprocess
import time

from sim_runner import ROOT, Simulator, GCC, dump, sha, source_inputs
from run_sail_event_comparison import compare, read_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', help='Run one generated name, e.g. e8_mf8')
    args = parser.parse_args()
    folder = ROOT / 'out/rva23/vector_state_differential'
    folder.mkdir(parents=True, exist_ok=True)
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    reference_path = ROOT / 'out/reference/sail-event-driver/report.json'
    reference = json.loads(reference_path.read_text(encoding='utf-8'))
    assert reference['passed']
    assert all(p in model['params'] for p in ['-GXLEN=64','-GHAS_H=1','-GHAS_V=1'])
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
    assert source_inputs(files) == model['inputs']
    runtime = {p:sha(ROOT / p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex',
        'scripts/reference/upstream_htif.ld','config/reference/sail-rv23.json',
        'scripts/run_sail_event_comparison.py']}
    config = ROOT / 'config/reference/sail-rv23.json'
    configs = []
    for name, numerator, denominator in [('mf8',1,8),('mf4',1,4),('mf2',1,2),('m1',1,1),('m2',2,1),('m4',4,1),('m8',8,1)]:
        for sew in [8,16,32,64]:
            if sew * denominator <= 64 * numerator:
                configs.append(dict(name=f'e{sew}_{name}', sew=sew, lmul=name,
                                    vlmax=128*numerator//(denominator*sew),vxrm=sew.bit_length()-4,
                                    vtype=((sew.bit_length()-4)<<3)|{'m1':0,'m2':1,'m4':2,'m8':3,'mf8':5,'mf4':6,'mf2':7}[name]))
    assert len(configs) == 22
    if args.case:
        configs = [c for c in configs if c['name']==args.case]
        assert len(configs)==1

    def fresh():
        for p,digest in {**model['inputs'],**runtime,**reference['inputs']}.items():
            assert sha(ROOT / p)==digest, p
        for m in [model,reference]:
            assert sha(ROOT / m['binary'])==m['binary_sha256']

    fresh()
    report = dict(passed=False,complete_profile_validation=False,
        scope='All 32 VLEN128 register bits and vector CSRs at five checkpoints per legal SEW/LMUL; exact undisturbed-policy integer state subset, not full V/H/FP differential coverage',
        model=model,reference_report_sha256=sha(reference_path),runtime_inputs=runtime,
        generator_sha256=sha(__file__),selected=configs,cases=[])
    report_path = folder / ('selected_report.json' if args.case else 'report.json')
    dump(report_path,report)
    with Simulator() as sim:
        ref_env = sim.env.copy()
        ref_env['PATH']='C:/rv_toolchains/cygwin-rv23/bin;'+os.environ['PATH']

        def one(case):
            dest=folder/case['name']
            dest.mkdir(parents=True,exist_ok=True)
            vtype=f'e{case["sew"]},{case["lmul"]},tu,mu'
            lines=['.section .text.init,"ax"','.option norvc','.option norelax','.globl _start','_start:',
                'la t0,fail','csrw mtvec,t0','li t0,0x600','csrw mstatus,t0',
                'li t0,-1','vsetvli zero,t0,e8,m1,tu,mu','csrw vstart,zero',
                f'li t0,{case["vxrm"]}','csrw vxrm,t0','csrw vxsat,zero','la t0,initial_vectors']
            for register in range(32):
                lines += [f'vl1re8.v v{register},(t0)','addi t0,t0,16']
            lines += ['li t0,-1',f'vsetvli s1,t0,{vtype}','jal ra,capture',
                'li t0,1','csrw vstart,t0','csrr a4,vstart',
                'vadd.vv v8,v16,v24,v0.t','jal ra,capture',
                'addi t0,s1,-1',f'vsetvli zero,t0,{vtype}','li a0,-1',
                'vsaddu.vx v8,v16,a0','jal ra,capture',
                'li t0,0',f'vsetvli zero,t0,{vtype}','vxor.vv v8,v16,v24','jal ra,capture',
                'li t0,-1',f'vsetvli zero,t0,{vtype}','li t0,1','csrw vstart,t0',
                'vrgather.vv v8,v16,v24','jal ra,capture',
                'la t0,tohost','li t1,1','sd t1,0(t0)','halt:j halt','capture:',
                'csrr a3,vl','csrr a3,vtype','csrr a3,vstart','csrr a3,vxrm',
                'csrr a3,vxsat','csrr a3,vcsr','csrr a3,vlenb','la t0,snapshot']
            for register in range(32):
                lines += [f'vs1r.v v{register},(t0)','addi t0,t0,16']
            lines += ['la t0,snapshot','li t1,64','.globl capture_ld','capture_ld:',
                'ld t2,0(t0)','addi t0,t0,8','addi t1,t1,-1','bnez t1,capture_ld','ret',
                'fail:','la t0,tohost','li t1,3','sd t1,0(t0)','j halt',
                '.section .tohost,"aw"','.balign 8','.globl tohost,fromhost',
                'tohost:.dword 0','fromhost:.dword 0','.section .data,"aw"',
                '.balign 16','initial_vectors:']
            values=[(i*37+(i//16)*13+0xaa)&255 for i in range(512)]
            for i in range(0,512,16):
                lines += ['.byte '+','.join(str(v) for v in values[i:i+16])]
            lines += ['.section .bss,"aw",@nobits','.balign 64','snapshot:.space 512']
            source,elf=dest/'test.S',dest/'test.elf'
            source.write_text('\n'.join(lines)+'\n',encoding='utf-8')
            compile_run,_=sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh','-mabi=lp64d',
                '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
                '-T','scripts/reference/upstream_htif.ld',source,'-o',elf],dest/'compile.log',60)
            sail_trace=dest/'sail_events.csv'
            # Use subprocess directly for the independent host environment;
            # other workers continue using sim.env for native RTL tools.
            started=time.time()
            with (dest/'sail.log').open('w',encoding='utf-8') as stream:
                result=subprocess.run([str(ROOT/reference['binary']),'--config',str(config),
                    '--commit-csv',str(sail_trace),'--inst-limit','1000000',str(elf)],
                    cwd=ROOT,env=ref_env,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
            assert result.returncode==0 and 'PASS Sail HTIF' in (dest/'sail.log').read_text(encoding='utf-8')
            sail_run=dict(passed=True,exit_code=0,seconds=round(time.time()-started,3),
                          log=(dest/'sail.log').relative_to(ROOT).as_posix(),log_sha256=sha(dest/'sail.log'))
            trace=dest/'commit.csv'
            run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
                f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit','+htif',
                '+timeout_cycles=3000000','+expected_exit_code=0'],dest/'rtl.log',240)
            assert 'PASS rv32_program_tb' in text
            left,right=read_csv(sail_trace),read_csv(trace)
            compared,mismatch=compare(left,right)
            assert mismatch is None,(case['name'],mismatch)
            names=subprocess.check_output([str(GCC/'riscv-none-elf-nm.exe'),str(elf)],text=True)
            load_pc=next(int(p[0],16) for line in names.splitlines() if len(p:=line.split())==3 and p[2]=='capture_ld')
            observed=[r for r in left if int(r['pc'],16)==load_pc]
            assert len(observed)==320 and all(r['rd_write']=='1' and r['trap']=='0' for r in observed)
            assert len({r['wdata'] for r in observed})>32
            csrs={address:[] for address in [0xc20,0xc21,0x008,0x00a,0x009,0x00f,0xc22]}
            for row in left:
                instruction=int(row['instruction'],16)
                address=instruction>>20
                if instruction&0x7f==0x73 and row['rd']=='13' and address in csrs:
                    csrs[address].append(int(row['wdata'],16))
            expected_csrs={0xc20:[case['vlmax'],case['vlmax'],case['vlmax']-1,0,case['vlmax']],
                0xc21:[case['vtype']]*5,0x008:[0]*5,0x00a:[case['vxrm']]*5,
                0x009:[0,0,1,1,1],0x00f:[(case['vxrm']<<1)|v for v in [0,0,1,1,1]],0xc22:[16]*5}
            assert csrs==expected_csrs,(case['name'],csrs,expected_csrs)
            row=dict(**case,passed=True,compared=compared,snapshots=5,snapshot_words=320,
                load_pc=load_pc,source_sha256=sha(source),elf_sha256=sha(elf),
                sail_trace_sha256=sha(sail_trace),rtl_trace_sha256=sha(trace),
                compile=compile_run,sail=sail_run,run=run,
                csr_snapshots={f'{address:03x}':values for address,values in csrs.items()})
            if case['name']=='e8_mf8':
                index=next(i for i,r in enumerate(left) if int(r['pc'],16)==load_pc)
                corrupted=[dict(r) for r in left]
                corrupted[index]['wdata']=f'{int(corrupted[index]["wdata"],16)^(1<<63):016x}'
                bad_index,bad=compare(corrupted,right)
                assert bad is not None and bad_index==index
                negative=dest/'corrupted_vector_word.csv'
                with negative.open('w',newline='',encoding='utf-8') as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(left[0]));writer.writeheader();writer.writerows(corrupted)
                row['negative_control']=dict(rejected=True,index=index,trace_sha256=sha(negative),mismatch=bad)
            dump(dest/'report.json',row)
            return row

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            pending={pool.submit(one,case):case['name'] for case in configs}
            for future in concurrent.futures.as_completed(pending):
                row=future.result();report['cases'].append(row)
                dump(report_path,report)
                print('PASS vector state',row['name'],row['compared'],'events, 320 observed words',flush=True)
    fresh()
    report['passed']=len(report['cases'])==len(configs)
    report['cases'].sort(key=lambda c:c['name'])
    report['events_compared']=sum(c['compared'] for c in report['cases'])
    report['snapshot_words']=sum(c['snapshot_words'] for c in report['cases'])
    dump(report_path,report)
    print('PASS vector state differential:',len(configs),'configurations,',report['snapshot_words'],'64-bit vector words',flush=True)


if __name__=='__main__':
    main()

"""Replay preserved vector-state fixtures with the other three VTA/VMA policies."""
import argparse
import concurrent.futures
import csv
import json
import os
import subprocess
import sys
import time

from sim_runner import ROOT, Simulator, GCC, dump, sha
from run_sail_event_comparison import normalize,read_csv
from vector_agnostic_policy import snapshots,validate,validate_transition,compare_snapshots


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case')
    parser.add_argument('--policy',choices=['ta_mu','tu_ma','ta_ma'])
    args=parser.parse_args()
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/audit_vector_state_differential.py')],cwd=ROOT,check=True)
    base_path=ROOT/'out/rva23/vector_state_differential/report.json'
    base=json.loads(base_path.read_text(encoding='utf-8'))
    ref_path=ROOT/'out/reference/sail-event-driver/report.json'
    reference=json.loads(ref_path.read_text(encoding='utf-8'))
    folder=ROOT/'out/rva23/vector_agnostic_differential'
    folder.mkdir(parents=True,exist_ok=True)
    cases=[]
    for policy,ta,ma in [('ta_mu',1,0),('tu_ma',0,1),('ta_ma',1,1)]:
        for original in base['cases']:
            if args.case and args.case!=original['name'] or args.policy and args.policy!=policy:
                continue
            cases.append(dict(name=policy+'/'+original['name'],base_name=original['name'],policy=policy,
                ta=ta,ma=ma,sew=original['sew'],lmul=original['lmul'],vlmax=original['vlmax'],
                vxrm=original['vxrm'],vtype=original['vtype']|(ta<<6)|(ma<<7),load_pc=original['load_pc']))
    assert cases
    inputs={path:sha(ROOT/path) for path in ['scripts/vector_agnostic_policy.py',
        'scripts/run_sail_event_comparison.py','config/reference/sail-rv23.json',
        'scripts/reference/upstream_htif.ld','tb/fixtures/bootrom/bootrom_host_jump64.hex']}
    report=dict(passed=False,complete_profile_validation=False,
        scope='Three agnostic policy combinations on the 22 SEW/LMUL fixtures; active data and permitted per-element old/all-ones values checked independently',
        generator_sha256=sha(__file__),base_report_sha256=sha(base_path),
        reference_report_sha256=sha(ref_path),inputs=inputs,selected=cases,cases=[])
    path=folder/('selected_report.json' if args.case or args.policy else 'report.json')
    dump(path,report)
    config=ROOT/'config/reference/sail-rv23.json'
    with Simulator() as sim:
        env=sim.env.copy();env['PATH']='C:/rv_toolchains/cygwin-rv23/bin;'+os.environ['PATH']

        def one(case):
            dest=folder/case['name'];dest.mkdir(parents=True,exist_ok=True)
            original=ROOT/'out/rva23/vector_state_differential'/case['base_name']/'test.S'
            text=original.read_text(encoding='utf-8')
            assert text.count(',tu,mu')==5
            source=dest/'test.S';elf=dest/'test.elf'
            replacement=','+('ta' if case['ta'] else 'tu')+','+('ma' if case['ma'] else 'mu')
            source.write_text(text.replace(',tu,mu',replacement),encoding='utf-8')
            compile_run,_=sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh','-mabi=lp64d',
                '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
                '-T','scripts/reference/upstream_htif.ld',source,'-o',elf],dest/'compile.log',60)
            ref_trace=dest/'sail_events.csv';started=time.time()
            with (dest/'sail.log').open('w',encoding='utf-8') as stream:
                result=subprocess.run([str(ROOT/reference['binary']),'--config',str(config),
                    '--commit-csv',str(ref_trace),'--inst-limit','1000000',str(elf)],
                    cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
            assert result.returncode==0 and 'PASS Sail HTIF' in (dest/'sail.log').read_text(encoding='utf-8')
            sail=dict(passed=True,exit_code=0,seconds=round(time.time()-started,3),
                log=(dest/'sail.log').relative_to(ROOT).as_posix(),log_sha256=sha(dest/'sail.log'))
            rtl_trace=dest/'commit.csv'
            run,output=sim.run([ROOT/base['model']['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
                f'+trace_file={rtl_trace.relative_to(ROOT).as_posix()}','+quiet_commit','+htif',
                '+timeout_cycles=3000000','+expected_exit_code=0'],dest/'rtl.log',240)
            assert 'PASS rv32_program_tb' in output
            left,right=read_csv(ref_trace),read_csv(rtl_trace)
            left_states,right_states=snapshots(left,case['load_pc']),snapshots(right,case['load_pc'])
            left_coverage,right_coverage=validate(case,left_states),validate(case,right_states)
            compared,differences=compare_snapshots(left,right,case['load_pc'],normalize)
            csrs={address:[] for address in ['c20','c21','008','00a','009','00f','c22']}
            for row in left:
                opcode=int(row['instruction'],16);address=f'{opcode>>20:03x}'
                if opcode&0x7f==0x73 and row['rd']=='13' and address in csrs:
                    csrs[address].append(int(row['wdata'],16))
            assert csrs=={'c20':[case['vlmax'],case['vlmax'],case['vlmax']-1,0,case['vlmax']],
                'c21':[case['vtype']]*5,'008':[0]*5,'00a':[case['vxrm']]*5,
                '009':[0,0,1,1,1],'00f':[(case['vxrm']<<1)|v for v in [0,0,1,1,1]],'c22':[16]*5}
            row=dict(**case,passed=True,compared=compared,snapshot_words=320,csr_snapshots=csrs,
                permitted_word_differences=differences,sail_policy_coverage=left_coverage,rtl_policy_coverage=right_coverage,
                source_sha256=sha(source),elf_sha256=sha(elf),sail_trace_sha256=sha(ref_trace),
                rtl_trace_sha256=sha(rtl_trace),compile=compile_run,sail=sail,run=run)
            if case['name']=='ta_ma/e8_mf8':
                controls=[]
                specs=[('allowed_tail',1,2,0xff,True,'tail_agnostic'),
                    ('bad_tail',1,2,0x7e,False,'tail_agnostic'),
                    ('bad_prestart',1,0,right_states[1][128]^1,False,'prestart'),
                    ('bad_active',1,1,right_states[1][129]^0x80,False,'active'),
                    ('bad_vl_zero',3,0,right_states[3][128]^1,False,'vl_zero')]
                for name,stage,index,value,accepted,category in specs:
                    altered=bytearray(right_states[stage]);altered[128+index]=value
                    filename=dest/(name+'.bin');filename.write_bytes(altered)
                    error=None
                    try:validate_transition(case,stage,right_states[stage-1],bytes(altered))
                    except ValueError as exception:error=str(exception)
                    assert (error is None)==accepted and (accepted or category in error)
                    controls.append(dict(name=name,stage=stage,index=index,accepted=accepted,
                        category=category,error=error,artifact=filename.relative_to(ROOT).as_posix(),sha256=sha(filename)))
                row['policy_controls']=controls
                # A legal all-ones tail choice may persist through later
                # undisturbed/VL=0 observations. Exercise that divergence too.
                forked=[dict(r) for r in left]
                load_indices=[i for i,r in enumerate(forked) if int(r['pc'],16)==case['load_pc']]
                for stage in [1,2,3,4]:
                    index=load_indices[stage*64+16]
                    value=int(forked[index]['wdata'],16)
                    forked[index]['wdata']=f'{(value&~(0xff<<16))|(0xff<<16):016x}'
                validate(case,snapshots(forked,case['load_pc']))
                accepted_count,accepted_differences=compare_snapshots(forked,right,case['load_pc'],normalize)
                assert accepted_count==compared and accepted_differences==4
                allowed_path=dest/'allowed_agnostic_choice.csv'
                with allowed_path.open('w',newline='',encoding='utf-8') as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(forked[0]));writer.writeheader();writer.writerows(forked)
                row['allowed_choice_control']=dict(accepted=True,permitted_word_differences=4,
                    artifact=allowed_path.relative_to(ROOT).as_posix(),sha256=sha(allowed_path))
            dump(dest/'report.json',row)
            return row

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            pending={pool.submit(one,case):case['name'] for case in cases}
            for future in concurrent.futures.as_completed(pending):
                row=future.result();report['cases'].append(row);dump(path,report)
                print('PASS vector agnostic',row['name'],'permitted word differences',row['permitted_word_differences'],flush=True)
    assert sha(base_path)==report['base_report_sha256'] and sha(ref_path)==report['reference_report_sha256']
    for p,h in {**inputs,**base['model']['inputs'],**reference['inputs']}.items():assert sha(ROOT/p)==h,p
    report['passed']=len(report['cases'])==len(cases)
    report['cases'].sort(key=lambda c:c['name'])
    report['events_compared']=sum(c['compared'] for c in report['cases'])
    report['snapshot_words']=sum(c['snapshot_words'] for c in report['cases'])
    dump(path,report)
    print('PASS vector agnostic differential:',len(cases),'cases,',report['snapshot_words'],'vector words',flush=True)


if __name__=='__main__':main()

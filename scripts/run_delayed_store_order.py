"""Whole-core older-store dependency delays with independent byte results."""
import argparse
import copy
import json
import re
import subprocess

from audit_hv_sail_fixture import check_fixture
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs

FOLDER=ROOT/'out/rva23/delayed_store_order'
TOP='rv23_delayed_store_order_tb'
VALUE=0x1234567887654380
MASK=(1<<64)-1
LOADS=[('lb',1,True),('lh',2,True),('lw',4,True),('ld',8,False),
       ('lbu',1,False),('lhu',2,False),('lwu',4,False)]


def cases():
    result=[]
    for delay in ('address','data'):
        for offset in (0,8,48,56):
            for store,size in [('sb',1),('sh',2),('sw',4),('sd',8)]:
                for load,width,signed in LOADS:
                    for side in (0,1):
                        start=8-size
                        index=8-width if side else 0
                        memory=bytearray([0xa5]*8)
                        memory[start:start+size]=VALUE.to_bytes(8,'little')[:size]
                        value=int.from_bytes(memory[index:index+width],'little')
                        if signed and value>>(width*8-1): value-=1<<(width*8)
                        result.append(dict(id=len(result)+1,delay=delay,offset=offset,store=store,size=size,
                            start=start,load=load,width=width,index=index,value=value&MASK,guard=int.from_bytes(memory,'little')))
    assert len(result)==448
    return result


def fixture(plan):
    lines=['.section .text.init,"ax"','.option norvc','.globl _start','_start:',
        'la t0,fail','csrw mtvec,t0']
    for c in plan:
        i=c['id'];base=0x800a0000+c['offset']
        numerator=(base+c['start'] if c['delay']=='address' else VALUE)*3
        lines += [f'li s4,{i}',f'li s0,{base:#x}','li t0,0xa5a5a5a5a5a5a5a5','sd t0,0(s0)',
            'fence rw,rw','ld t2,0(s0)',f'li s1,{VALUE:#x}','li s2,3',f'li s3,{numerator:#x}',
            f'div_{i}:div s3,s3,s2']
        lines += [f'store_{i}:{c["store"]} s1,0(s3)'] if c['delay']=='address' else [f'store_{i}:{c["store"]} s3,{c["start"]}(s0)']
        lines += [f'probe_{i}:{c["load"]} t2,{c["index"]}(s0)',f'li t3,{c["value"]:#x}','bne t2,t3,fail',
            f'guard_{i}:ld t2,0(s0)',f'li t3,{c["guard"]:#x}','bne t2,t3,fail']
    lines += ['li t1,1','j finish','fail:slli t1,s4,1','ori t1,t1,1',
        'finish:la t0,tohost','sd t1,0(t0)','halt:j halt','.section .tohost,"aw"',
        '.balign 8','.globl tohost,fromhost','tohost:.dword 0','fromhost:.dword 0']
    return '\n'.join(lines)+'\n'


def symbols():
    text=subprocess.check_output([str(GCC/'riscv-none-elf-nm.exe'),'-n',str(FOLDER/'test.elf')],text=True)
    return {p[2]:int(p[0],16) for line in text.splitlines() if len(p:=line.split())==3}


def inspect(rows,plan,labels):
    reads={labels[f'{kind}_{c["id"]}']:c['value' if kind=='probe' else 'guard'] for c in plan for kind in ('probe','guard')}
    seen=set()
    for r in rows:
        if int(r['pc'],16)<0x80000000:continue
        assert r['trap']=='0',r
        pc=int(r['pc'],16)
        if pc in reads:
            assert pc not in seen and r['rd_write']=='1' and r['rd']=='7' and r['rd_fp']=='0'
            assert int(r['wdata'],16)==reads[pc],r
            seen.add(pc)
    assert seen==set(reads)
    return dict(cases=len(plan),load_results=len(seen),delay_kinds=['address','data'],store_forms=4,load_forms=7)


def verify_traces(sail,rtl):
    rows=read_csv(rtl);count,mismatch=compare(read_csv(sail),rows)
    assert mismatch is None,mismatch
    plan,labels=cases(),symbols()
    result=inspect(rows,plan,labels)
    controls=[]
    for kind in ('probe','guard'):
        broken=copy.deepcopy(rows)
        row=next(r for r in broken if int(r['pc'],16)==labels[f'{kind}_1'])
        row['wdata']=f'{int(row["wdata"],16)^1:016x}'
        try:inspect(broken,plan,labels)
        except AssertionError:controls.append(kind)
        else:raise AssertionError('Incorrect load result accepted')
    return dict(**result,matched_events=count,rejected_mutations=controls)


def verify_pipeline(log):
    m=re.search(r'DELAYED_STORE_ORDER unknown=(\d+) partial=(\d+) data=(\d+) div_overlap=(\d+) older_sq_div=(\d+)',log)
    assert m and 'PASS rv32_program_tb' in log
    values=dict(zip(('unknown','partial','data','div_overlap','older_sq_div'),map(int,m.groups())))
    assert all(value>0 for value in values.values()),values
    return values


def files():
    return (ROOT/'rtl/filelist.f').read_text().splitlines()+[
        'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv','tb/rv32_program_tb.sv',
        f'tb/{TOP}.sv','tb/e2e/dpi/elf_loader.cpp']


def check():
    record=json.loads((FOLDER/'report.json').read_bytes())
    assert record['passed']
    assert record['outcomes']==check_fixture(FOLDER,__file__,fixture(cases()),verify_traces)
    model=record['pipeline_model']
    assert model['inputs']==source_inputs(files()) and model['top']==TOP
    assert sha(ROOT/model['binary'])==model['binary_sha256']
    for step in (model['compile'],model['build'],record['pipeline_run']):
        assert step['passed'] and step['exit_code']==0 and sha(ROOT/step['log'])==step['log_sha256']
    trace=FOLDER/'pipeline_commit.csv'
    assert sha(trace)==record['pipeline_trace_sha256']
    assert verify_traces(FOLDER/'sail.csv',trace)==record['outcomes']
    log=(ROOT/record['pipeline_run']['log']).read_text()
    assert verify_pipeline(log)==record['pipeline']
    for kind in ('unknown','partial','data','div_overlap','older_sq_div'):
        broken=re.sub(r'\b'+kind+r'=\d+',kind+'=0',log)
        try:verify_pipeline(broken)
        except AssertionError:pass
        else:raise AssertionError('Missing pipeline wait witness accepted')
    return record['outcomes'],record['pipeline']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    FOLDER.mkdir(parents=True,exist_ok=True)
    if not args.check:
        source=FOLDER/'test.S';source.write_text(fixture(cases()),encoding='utf-8')
        run_fixture(source,FOLDER,__file__,verify_traces,source_dependencies=['scripts/audit_hv_sail_fixture.py'],timeout_cycles=2000000)
        record=json.loads((FOLDER/'report.json').read_bytes());record['passed']=False;dump(FOLDER/'report.json',record)
        with Simulator() as sim:
            model=sim.build('rv23_delayed_store_order',TOP,files())
            trace=FOLDER/'pipeline_commit.csv'
            run,log=sim.run([ROOT/model['binary'],f'+elf={(FOLDER/"test.elf").relative_to(ROOT).as_posix()}',
                f'+trace_file={trace.relative_to(ROOT).as_posix()}','+htif','+quiet_commit',
                '+timeout_cycles=2000000','+expected_exit_code=0'],FOLDER/'pipeline.log',120)
        record.update(passed=True,pipeline_model=model,pipeline_run=run,pipeline=verify_pipeline(log),pipeline_trace_sha256=sha(trace))
        dump(FOLDER/'report.json',record)
    print('PASS delayed older store/load ordering',*check(),flush=True)


if __name__=='__main__':main()

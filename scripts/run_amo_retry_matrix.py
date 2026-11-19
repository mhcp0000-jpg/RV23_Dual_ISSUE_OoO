"""Real AXI xbar/bridge/SRAM AMO interference and retry matrix."""
import argparse
import json
import re

from sim_runner import ROOT, Simulator, dump, sha, source_inputs

FOLDER=ROOT/'out/rva23/amo_retry_matrix'
TOP='rv23_amo_retry_matrix_tb'
FILES=['rtl/rv_ooo_pkg.sv','rtl/soc/rv_soc_pkg.sv','rtl/soc/rv23_pkg.sv',
    'rtl/soc/rv_axi4_if.sv','rtl/soc/rv_local_mem_if.sv','rtl/soc/rv_axi_xbar.sv',
    'rtl/soc/rv_axi_error_slave.sv','rtl/soc/rv_axi_to_local_bridge.sv',
    'rtl/soc/rv_sram_1r1w.sv','rtl/soc/rv23_sram.sv','rtl/soc/rv23_atomic_engine.sv',f'tb/{TOP}.sv']
OPS=(0,1,4,8,12,16,20,24,28)


def signed(value,bits):
    return value-(1<<bits) if value>>(bits-1) else value


def expected(shape,op,kind,rounds):
    data=bytearray((0x8123456789abcdef).to_bytes(8,'little'))
    shift=32 if shape==2 else 0
    if kind<2:
        for round_id in range(1,rounds+1):
            other=(0x90abcdef87654321 ^ (0x0101010101010101*round_id)).to_bytes(8,'little')
            for byte in range(8):
                if kind==0 or byte==(shift//8 if shape else 2):data[byte]=other[byte]
    width=4 if shape else 8
    a=int.from_bytes(data[shift//8:shift//8+width],'little')
    b=0xfedcba9876543210 & ((1<<(width*8))-1)
    if op==0:value=a+b
    elif op==1:value=b
    elif op==4:value=a^b
    elif op==8:value=a|b
    elif op==12:value=a&b
    elif op==16:value=min(signed(a,width*8),signed(b,width*8))
    elif op==20:value=max(signed(a,width*8),signed(b,width*8))
    elif op==24:value=min(a,b)
    else:assert op==28;value=max(a,b)
    old=(signed(a,32) if shape else a)&((1<<64)-1)
    data[shift//8:shift//8+width]=(value&((1<<(width*8))-1)).to_bytes(width,'little')
    return old,int.from_bytes(data,'little')


def verify(log):
    rows=re.findall(r'^AMO_RETRY shape=(\d+) op=(\d+) kind=(\d+) rounds=(\d+) reads=(\d+) failed=(\d+) writes=(\d+) old=([\da-f]+) memory=([\da-f]+)$',log,re.M)
    assert f'PASS {TOP} cases=270' in log and len(rows)==270
    seen=set();failures=0;retries=0;writes=0
    for *fields,old,memory in rows:
        shape,op,kind,rounds,reads,failed,actual_writes=map(int,fields)
        key=shape,op,kind,rounds
        assert key not in seen and shape in range(3) and op in OPS and kind in range(5) and rounds in (1,2)
        assert (reads,failed,actual_writes)==(rounds+1 if kind<3 else 1,rounds if kind<3 else 0,1+(0 if kind==4 else rounds))
        assert (int(old,16),int(memory,16))==expected(*key),key
        seen.add(key);failures+=failed;retries+=int(kind<3);writes+=actual_writes
    assert seen=={(s,o,k,r) for s in range(3) for o in OPS for k in range(5) for r in (1,2)}
    return dict(cases=len(seen),interfered_cases=retries,failed_exclusives=failures,actual_writes=writes,read_only_cases=54,unrelated_line_cases=54)


def check(report):
    assert report['passed'] and report['driver_sha256']==sha(__file__)
    model=report['model'];assert model['inputs']==source_inputs(FILES) and model['top']==TOP
    assert sha(ROOT/model['binary'])==model['binary_sha256']
    for step in (model['compile'],model['build'],report['run']):
        assert step['passed'] and step['exit_code']==0 and sha(ROOT/step['log'])==step['log_sha256']
    log=(ROOT/report['run']['log']).read_text()
    assert verify(log)==report['outcomes']
    controls=[]
    for key in ('reads','failed','writes','old','memory'):
        pattern=r'('+key+r'=)([\da-f]+)'
        broken=re.sub(pattern,lambda m:m[1]+str(int(m[2],16 if key in ('old','memory') else 10)+1),log,count=1)
        assert broken!=log
        try:verify(broken)
        except AssertionError:controls.append(key)
        else:raise AssertionError('Corrupt retry witness accepted')
    return report['outcomes'],controls


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    FOLDER.mkdir(parents=True,exist_ok=True)
    if args.check:report=json.loads((FOLDER/'report.json').read_bytes())
    else:
        with Simulator() as sim:
            model=sim.build('rv23_amo_retry_matrix',TOP,FILES)
            run=sim.simulate(model)
        report=dict(passed=True,complete_profile_validation=False,scope='Real production AMO engine/xbar/exclusive bridge/SRAM components, nine operations and D/W-low/W-high interference; not whole-core issue/trap, all bus interleavings or liveness proof',
            model=model,run=run,outcomes=verify((ROOT/run['log']).read_text()),driver_sha256=sha(__file__))
        dump(FOLDER/'report.json',report)
    print('PASS AMO retry matrix',*check(report),flush=True)


if __name__=='__main__':main()

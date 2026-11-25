"""Audit two completed same-ELF runs without rewriting or rerunning either."""
import argparse,json,re
from sim_runner import ROOT,sha,source_inputs,dump

parser=argparse.ArgumentParser()
parser.add_argument('--before',required=True)
parser.add_argument('--after',required=True)
parser.add_argument('--before-model',required=True,help='Captured executable/model with historical source hashes')
parser.add_argument('--expected-changes',nargs='+',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
before=json.loads((ROOT/args.before).read_bytes())
after=json.loads((ROOT/args.after).read_bytes())
captured=json.loads((ROOT/args.before_model).read_bytes())
assert before['passed'] and after['passed']
assert before['iterations']==after['iterations'] and before['elf_sha256']==after['elf_sha256']
assert sha(ROOT/f'out/performance/rv64_coremark/o3_rvv_{after["iterations"]}/coremark.elf')==after['elf_sha256']
assert before['instructions']==after['instructions']
assert captured['params']==before['model']['params']==after['model']['params']
assert captured['inputs']==before['model']['inputs']
assert captured['binary_sha256']==before['model']['binary_sha256']
assert sha(ROOT/captured['binary'])==captured['binary_sha256']
assert sha(ROOT/after['model']['binary'])==after['model']['binary_sha256']
assert after['model']['inputs']==source_inputs(after['model']['inputs'])
assert set(captured['inputs'])==set(after['model']['inputs'])
changed={p:dict(before=h,after=after['model']['inputs'][p]) for p,h in captured['inputs'].items()
         if h!=after['model']['inputs'][p]}
assert set(changed)==set(args.expected_changes),changed
for record in [before,after]:
    assert sha(ROOT/record['run']['log'])==record['run']['log_sha256']
    packet=record['packet']
    log=(ROOT/record['run']['log']).read_text(encoding='utf-8')
    assert 'PASS rv32_program_tb' in log
    words=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]',log)]
    assert words[words.index(0x434d0001):][:12]==packet
    assert packet[:2]==[0x434d0001,record['iterations']]
    assert packet[6:10]==[0xe9f5,0xe714,0x1fd7,0x8e3a] and packet[11]&0x17==1
    assert record['cycles']==packet[2]+(packet[3]<<32)
    assert record['instructions']==packet[4]+(packet[5]<<32)
dump(ROOT/args.output,dict(passed=True,certified_score=False,
    scope='Derived comparison of completed measured runs on the same fixed ELF; captured before executable, exact source-change set, params, CRC and log hashes checked. Not a new execution or physical timing sign-off.',
    driver_sha256=sha(__file__),before_report=args.before,before_report_sha256=sha(ROOT/args.before),
    after_report=args.after,after_report_sha256=sha(ROOT/args.after),
    before_model_sha256=sha(ROOT/args.before_model),changed_inputs=changed,
    elf_sha256=after['elf_sha256'],iterations=after['iterations'],instructions=after['instructions'],
    before_cycles=before['cycles'],after_cycles=after['cycles'],
    before_ipc=before['instructions']/before['cycles'],after_ipc=after['instructions']/after['cycles'],
    cycle_reduction_percent=100*(before['cycles']-after['cycles'])/before['cycles'],
    speedup=before['cycles']/after['cycles']))
print('PASS completed-run comparison',before['cycles'],'->',after['cycles'],
      'cycle reduction %',100*(before['cycles']-after['cycles'])/before['cycles'],flush=True)

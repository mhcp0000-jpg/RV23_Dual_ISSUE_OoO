"""Compare every user-test retirement and scalar writeback against official Sail."""
import argparse
import csv
import json
from sim_runner import ROOT, sha, dump

parser=argparse.ArgumentParser()
parser.add_argument('--case')
parser.add_argument('--report')
parser.add_argument('--output')
args=parser.parse_args()
folder=ROOT/'out/rva23/sail_upstream_comparison'
report_path=ROOT/args.report if args.report else folder/'report.json'
report=json.loads(report_path.read_text(encoding='utf-8'))
assert report['passed'] and not report['reference_only']
cases=[case for case in report['cases'] if not case['name'].startswith(('rv64mi/','rv64si/'))]
if args.case:cases=[case for case in cases if case['name']==args.case]
assert cases
if not args.case:assert len(cases)==152
for name,digest in report['inputs'].items():assert sha(ROOT/name)==digest,name
model=report['model']
for name,digest in model['inputs'].items():assert sha(ROOT/name)==digest,name
assert sha(ROOT/model['binary'])==model['binary_sha256']
assert sha(ROOT/report['reference']['binary'])==report['reference']['binary_sha256']

def normalize(row):
    pc=int(row['pc'],16);instruction=int(row['instruction'],16)
    if instruction&3!=3:instruction&=0xffff
    trap=row['trap']=='1'
    write=row['rd_write']=='1' and (row['rd_fp']=='1' or int(row['rd'])!=0)
    writeback=(int(row['rd_fp']),int(row['rd']),int(row['wdata'],16)) if write else None
    return dict(pc=pc,instruction=instruction,trap=trap,cause=int(row['cause']) if trap else 0,
                writeback=writeback)

audit=dict(passed=False,scope='Exact 152 user-test Sail/RTL retirement prefixes: PC, raw instruction, trap/cause, scalar integer/FP destination and 64-bit value. Boot ROM excluded; asynchronous HTIF completion tails excluded; no cycle comparison or M/S-test trace-equivalence claim.',
           input_report=report_path.relative_to(ROOT).as_posix(),input_report_sha256=sha(report_path),
           generator_sha256=sha(__file__),cases=[])
path=ROOT/args.output if args.output else folder/('selected_retirement_audit.json' if args.case else 'retirement_audit.json')
failures=[]
for case in cases:
    assert case['reference_passed'] and case['rtl_passed']
    for key in ['elf','sail_trace','rtl_trace']:
        assert sha(ROOT/case[key])==case[key+'_sha256'],(case['name'],key)
    compared=0;mismatch=None
    with (ROOT/case['sail_trace']).open(newline='') as left,(ROOT/case['rtl_trace']).open(newline='') as right:
        reference=csv.DictReader(left);actual=csv.DictReader(right)
        first=next(reference)
        candidate=next(actual)
        while int(candidate['pc'],16)!=int(first['pc'],16):candidate=next(actual)
        for expected in [first]:
            if normalize(expected)!=normalize(candidate):mismatch=dict(index=compared,sail=expected,rtl=candidate)
            compared+=1
        if mismatch is None:
            for expected in reference:
                candidate=next(actual,None)
                if candidate is None or normalize(expected)!=normalize(candidate):
                    mismatch=dict(index=compared,sail=expected,rtl=candidate);break
                compared+=1
    row=dict(name=case['name'],passed=mismatch is None,compared=compared,
             elf_sha256=case['elf_sha256'],sail_trace_sha256=case['sail_trace_sha256'],
             rtl_trace_sha256=case['rtl_trace_sha256'])
    if mismatch:
        row['first_mismatch']=mismatch;failures.append(case['name'])
        print('FAIL differential retirement',case['name'],compared,flush=True)
    audit['cases'].append(row)
    dump(path,audit)
audit['passed']=not failures
audit['retirements_compared']=sum(row['compared'] for row in audit['cases'])
dump(path,audit)
assert not failures,failures
print('PASS exact Sail/RTL retirement comparison',len(cases),'ELFs',audit['retirements_compared'],'instructions',flush=True)

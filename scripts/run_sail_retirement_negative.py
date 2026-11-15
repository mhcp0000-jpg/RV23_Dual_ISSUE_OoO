"""Require the real differential audit to reject a copied 64-bit writeback corruption."""
import csv
import json
import sys
from sim_runner import ROOT, Simulator, sha, dump

base=ROOT/'out/rva23/sail_upstream_comparison/report.json'
report=json.loads(base.read_text(encoding='utf-8'))
assert report['passed']
case=next(case for case in report['cases'] if case['name']=='rv64ui/add')
original=ROOT/case['rtl_trace'];assert sha(original)==case['rtl_trace_sha256']
with original.open(newline='') as stream:
    reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
index=next(index for index,row in enumerate(rows) if int(row['pc'],16)>=0x80000000
           and row['gpr_we']=='1' and int(row['wdata'],16)>=1<<32)
before=rows[index]['wdata']
rows[index]['wdata']=f'{int(before,16)^(1<<40):016x}'
folder=ROOT/'out/negative_controls/sail_retirement_checker_20261102'
folder.mkdir(parents=True,exist_ok=True)
copied=folder/'corrupted.csv'
with copied.open('w',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
case={**case,'rtl_trace':copied.relative_to(ROOT).as_posix(),'rtl_trace_sha256':sha(copied)}
modified={**report,'cases':[case]}
input_path=folder/'input_report.json';dump(input_path,modified)
with Simulator() as sim:
    run,output=sim.run([sys.executable,ROOT/'scripts/audit_sail_retirements.py','--case','rv64ui/add',
        '--report',input_path.relative_to(ROOT).as_posix(),
        '--output',(folder/'rejected_comparison.json').relative_to(ROOT).as_posix()],
        folder/'rejection.log',60,expected_failure='FAIL differential retirement rv64ui/add')
assert sha(original)==report['cases'][next(i for i,c in enumerate(report['cases']) if c['name']=='rv64ui/add')]['rtl_trace_sha256']
dump(folder/'report.json',dict(passed=True,scope='A copied real RTL trace with one high writeback bit flipped is rejected by the actual Sail retirement audit; original evidence is unchanged',
    generator_sha256=sha(__file__),audit_sha256=sha(ROOT/'scripts/audit_sail_retirements.py'),
    original_report_sha256=sha(base),original_trace=original.relative_to(ROOT).as_posix(),original_trace_sha256=sha(original),
    corrupted_trace=copied.relative_to(ROOT).as_posix(),corrupted_trace_sha256=sha(copied),
    input_report=input_path.relative_to(ROOT).as_posix(),input_report_sha256=sha(input_path),
    rejected_report=(folder/'rejected_comparison.json').relative_to(ROOT).as_posix(),
    rejected_report_sha256=sha(folder/'rejected_comparison.json'),
    mutation=dict(row=index,pc=rows[index]['pc'],before=before,after=rows[index]['wdata'],bit=40),run=run))
print('PASS differential negative control: 64-bit writeback corruption rejected; original trace intact',flush=True)

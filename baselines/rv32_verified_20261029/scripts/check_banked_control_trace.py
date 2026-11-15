"""Check identical architectural control stream in the CoreMark timed body.

Data values derived from mcycle legitimately differ. This checks retirement
order/PC/opcode/destination/trap/CSR metadata, not a general ISA equivalence.
"""
import csv,itertools,json,subprocess
from sim_runner import ROOT,GCC,sha,dump
path=ROOT/'out/performance/banked_after/report.json'
report=json.loads(path.read_text());assert report['passed']
case=next(c for c in report['cases'] if c['iterations']==2)
elf=ROOT/case['elf']
symbols=subprocess.check_output([str(GCC/'riscv-none-elf-nm.exe'),str(elf)],text=True)
def address(name):return next(x.split()[0].lower() for x in symbols.splitlines() if x.endswith(' '+name))
start,stop=address('start_time'),address('stop_time')
fields=['pc','instruction','rd_write','rd_fp','rd','trap','cause','tval','csr_valid','csr_we','csr_addr']
def rows(file):
    active=False
    with file.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row['pc']==start:active=True
            if active and row['pc']==stop:return
            if active:
                # Non-writing instructions have no architectural destination.
                if row['rd_write']=='0':row['rd']='-';row['rd_fp']='-'
                if row['csr_valid']=='0':row['csr_we']='-';row['csr_addr']='-'
                yield tuple(row[k] for k in fields)
before=ROOT/'out/performance/banked_after/before_2/commit.csv'
after=ROOT/'out/performance/banked_after/after_2/commit.csv'
count=0
for index,(a,b) in enumerate(itertools.zip_longest(rows(before),rows(after))):
    assert a==b,('Retirement control mismatch',index,a,b)
    count+=1
assert count>500000
case['control_stream']={'passed':True,'instructions':count,'fields':fields,
    'scope':'start_time entry through stop_time entry; excludes stop_time; timing-derived operand data excluded',
    'before_trace':before.relative_to(ROOT).as_posix(),'before_trace_sha256':sha(before),
    'after_trace':after.relative_to(ROOT).as_posix(),'after_trace_sha256':sha(after)}
# The preserved 10-iteration baseline log must stay bound to its snapshot,
# independent of a later run of the generic iteration runner.
ten=next(c for c in report['cases'] if c['iterations']==10)
log=ROOT/'out/performance/banked_before/out/performance/iterations/iter_10/simulation.log'
assert sha(log)==ten['before']['run']['log_sha256']
ten['before']['run']['log']=log.relative_to(ROOT).as_posix()
report['before_source_root']='out/performance/banked_before'
report['before_model']='out/performance/banked_before/out/programs/model.json'
dump(path,report)
print('PASS identical timed-body retirement control metadata:',count,'instructions')

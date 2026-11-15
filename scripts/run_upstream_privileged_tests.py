"""Reviewed upstream M/S tests for this Svade, assisted-misalignment platform."""
import json,subprocess,sys
from sim_runner import ROOT,sha,dump

names=['rv64mi/'+name for name in ['csr','mcsr','illegal','ma_fetch','scall','sbreak','zicntr','instret_overflow','pmpaddr']]
names+=['rv64si/'+name for name in ['csr','dirty','icache-alias','ma_fetch','scall','wfi','sbreak']]
folder=ROOT/'out/rva23/upstream_riscv_tests'
report=dict(passed=False,scope='16 unmodified upstream M/S tests with reviewed platform assumptions; not complete privileged architecture certification',
            generator_sha256=sha(__file__),cases=[])
path=ROOT/'out/rva23/upstream_privileged_evidence.json'
dump(path,report)
for name in names:
    subprocess.run([sys.executable,str(ROOT/'scripts/run_upstream_riscv_tests.py'),'--case',name,'--resume'],cwd=ROOT,check=True)
    result=json.loads((folder/name/'report.json').read_text(encoding='utf-8'))
    assert result['passed']
    report['cases'].append(dict(name=name,report_sha256=sha(folder/name/'report.json'),
                               inputs=result['inputs'],binary_sha256=result['binary_sha256']))
    dump(path,report)
report['passed']=True;dump(path,report)
print('PASS 16 upstream M/S privilege, CSR, trap, WFI, Sv39, Svade and counter tests',flush=True)

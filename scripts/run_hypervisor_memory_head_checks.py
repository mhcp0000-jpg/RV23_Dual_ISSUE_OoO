"""Guest element owner: natural MMIO, PMP R+X, pointer masking and byte assist.

This Bare-mode component check does not establish guest translation or H core
integration. Execute-permission translation requires the HLVX walker path.
"""
import hashlib,re
from sim_runner import ROOT,Simulator,dump
results=[]
with Simulator() as sim:
  for fast in [0,1]:
    model=sim.build('rva23_hypervisor_memory_head'+('' if fast else '_slow'),'rv23_hypervisor_memory_head_tb',[
        'rtl/rv_ooo_pkg.sv','rtl/backend/rv_pmp.sv','rtl/soc/rv23_pointer_mask.sv',
        'rtl/backend/rv23_hypervisor_memory_head.sv','tb/unit/backend/rv23_hypervisor_memory_head_tb.sv'],[f'-GFAST_BARE={fast}'])
    model['run']=sim.simulate(model);model['passed']=True
    log=(ROOT/model['run']['log']).read_text()
    m=re.search(r'checks=(\d+) requests=(\d+) cycles=(\d+)',log);assert m
    transactions=re.findall(r'^HEAD_ACCESS .+$',log,re.M);assert transactions
    results.append(dict(fast=bool(fast),model=model,checks=int(m[1]),requests=int(m[2]),cycles=int(m[3]),
        transactions=transactions,transaction_sha256=hashlib.sha256('\n'.join(transactions).encode()).hexdigest()))
assert results[0]['transactions']==results[1]['transactions']
assert results[0]['checks']==results[1]['checks'] and results[0]['requests']==results[1]['requests']
assert results[1]['cycles']<results[0]['cycles']
dump(ROOT/'out/rva23/hypervisor_memory_head.json',results[1]['model'])
dump(ROOT/'out/rva23/hypervisor_memory_head_bare_compare.json',dict(passed=True,
    scope='Same directed Bare owner stream with FAST_BARE=0/1; exact physical transaction payload/order match and independent data/fault checks, not full profile or physical timing sign-off',results=results))
print('PASS guest memory owner Bare mode: natural MMIO/PMP R+X/PMM; native guest integration has separate evidence',flush=True)
print('PASS identical physical transactions; cycles',results[0]['cycles'],'->',results[1]['cycles'],flush=True)

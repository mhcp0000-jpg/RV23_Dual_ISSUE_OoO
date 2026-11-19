"""Directed arithmetic and fixed-latency checks for iterative vector division."""
import re
from sim_runner import ROOT, Simulator, dump

with Simulator() as sim:
    model=sim.build('vector_divider','rv_vector_divider_tb',[
        'rtl/rv_ooo_pkg.sv','rtl/backend/rv_divider.sv','rtl/backend/rv_vector_divider.sv','tb/rv_vector_divider_tb.sv'])
    run=sim.simulate(model)
log=(ROOT/run['log']).read_text()
rows=re.findall(r'VDIV size=(\d+) op=(\d+) a=([\da-f]+) b=([\da-f]+) result=([\da-f]+) cycles=(\d+)',log)
assert len(rows)==128
for size,op,a,b,result,cycles in rows:
    size,op=int(size),int(op);bits=8<<size;mask=(1<<bits)-1
    a,b=int(a,16)&mask,int(b,16)&mask
    if op<2:
        a=a-(1<<bits) if a>>(bits-1) else a
        b=b-(1<<bits) if b>>(bits-1) else b
    q=(-1 if (a<0)!=(b<0) else 1)*(abs(a)//abs(b)) if b else -1
    expected=(a-q*b if op&1 and b else a if op&1 else q)&mask
    assert int(result,16)==expected and int(cycles)==68,(size,op,a,b,result,expected)
dump(ROOT/'out/rva23/vector_divider.json',dict(passed=True,scope='128 component cases; not production vector integration or physical timing sign-off',
    model=model,run=run,cases=len(rows),latency=68))
print('PASS iterative vector divider 128 cases; fixed 68-cycle response and held result')

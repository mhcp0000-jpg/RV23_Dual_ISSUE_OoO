"""Exercise aligned instruction fetch during concurrent debug AXI writes."""

from sim_runner import ROOT, Simulator, dump


top = 'rv23_instruction_fetch_atomic_tb'
files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines()
with Simulator() as sim:
    result = sim.build(top, top, files + [f'tb/{top}.sv'])
    result['run'] = sim.simulate(result)
    result['passed'] = True
    dump(ROOT / f'out/regression/{top}/report.json', result)
print(*result['run']['witnesses'], sep='\n', flush=True)

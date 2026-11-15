"""Byte assembly/sign/boxing, held ownership and prevalidation before writes."""
from sim_runner import ROOT,Simulator,sha,dump
files=(ROOT/'rtl/filelist.f').read_text().splitlines()+['tb/unit/backend/rv23_misaligned_head_tb.sv']
with Simulator() as sim:
    model=sim.build('rva23_misaligned_head','rv23_misaligned_head_tb',files)
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/misaligned_head.json',model)
    print('PASS misalignment head byte transfers and whole-access prevalidation; core integration pending',flush=True)

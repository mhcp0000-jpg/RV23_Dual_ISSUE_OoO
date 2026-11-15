"""Build a full-profile ACT4 DUT harness with the existing 1 MiB SRAM loader."""
import json
from sim_runner import ROOT,Simulator,dump,sha,source_inputs

base=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
files=(ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/e2e/rv_act4_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
folder=ROOT/'out/act4/dut';folder.mkdir(parents=True,exist_ok=True)
path=folder/'model.json';old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
with Simulator() as sim:
    if old and old['inputs']==source_inputs(files) and old['params']==base['params'] and sha(ROOT/old['binary'])==old['binary_sha256']:
        model=old
    else:model=sim.build('act4_rva23_core','rv_act4_program_tb',files,base['params'])
    dump(path,model)
    record=sim.simulate(model,['+elf=out/rva23/profile_scalar/instructions.elf','+quiet_commit','+timeout_cycles=4000000'],label='harness_smoke')
    model['smoke']=record;model['passed']=True;dump(path,model)
print('PASS full H/V ACT4 DUT harness smoke',flush=True)

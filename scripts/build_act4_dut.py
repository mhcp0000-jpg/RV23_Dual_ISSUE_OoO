"""Build a full-profile ACT4 DUT harness with the existing 1 MiB SRAM loader."""
import json
from sim_runner import ROOT,Simulator,dump,sha,source_inputs

base=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
assert base['inputs']==source_inputs(base['inputs'])
assert sha(ROOT/base['binary'])==base['binary_sha256']
files=(ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/e2e/rv_act4_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
folder=ROOT/'out/act4/dut';folder.mkdir(parents=True,exist_ok=True)
path=folder/'model.json';old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
inputs=source_inputs(files,['rtl/filelist.f'])
smoke_inputs=source_inputs(['out/rva23/profile_scalar/instructions.elf',
    'tb/fixtures/bootrom/bootrom_host_jump64.hex','scripts/build_act4_dut.py'])

def save(model):
    pending=path.with_suffix('.json.tmp')
    dump(pending,model);pending.replace(path)

def compiled(model):
    return bool(model and model.get('inputs')==inputs and model.get('params')==base['params'] and
        (ROOT/model['binary']).is_file() and sha(ROOT/model['binary'])==model['binary_sha256'])

def smoke_cached(model):
    if not compiled(model) or not model.get('passed') or model.get('smoke_inputs')!=smoke_inputs:return False
    record=model.get('smoke',{})
    log=ROOT/record.get('log','__missing_smoke_log__')
    return (record.get('passed') is True and record.get('exit_code')==0 and
        record.get('expected_failure') is None and log.is_file() and
        sha(log)==record.get('log_sha256') and 'data=0x50534331' in log.read_text(encoding='utf-8'))

if smoke_cached(old):
    # Preserve exact manifest bytes: Linux binds base_model_sha256 to this file.
    print('PASS full H/V ACT4 DUT harness smoke (source-bound cached result)',flush=True)
    raise SystemExit(0)

with Simulator() as sim:
    if compiled(old):
        model=old
    else:model=sim.build('act4_rva23_core','rv_act4_program_tb',files,base['params'],['rtl/filelist.f'])
    model['passed']=False;save(model)
    record=sim.simulate(model,['+elf=out/rva23/profile_scalar/instructions.elf','+quiet_commit','+timeout_cycles=4000000'],label='harness_smoke')
    assert 'data=0x50534331' in (ROOT/record['log']).read_text(encoding='utf-8')
    assert inputs==source_inputs(files,['rtl/filelist.f']) and smoke_inputs==source_inputs(smoke_inputs)
    model['smoke']=record;model['smoke_inputs']=smoke_inputs;model['passed']=True;save(model)
print('PASS full H/V ACT4 DUT harness smoke',flush=True)

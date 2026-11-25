"""Require an isolated zero-data wakeup implementation to fail the same ELF."""
import json
from sim_runner import ROOT,Simulator,dump,sha,source_inputs

folder=ROOT/'out/negative_controls/vector_system_wake';folder.mkdir(parents=True,exist_ok=True)
positive_path=ROOT/'out/rva23/vector_scalar_overlap/report.json'
positive=json.loads(positive_path.read_bytes());assert positive['passed']
elf=ROOT/'out/rva23/vector_scalar_overlap/test.elf';assert sha(elf)==positive['elf_sha256']
current=positive['model'];assert current['inputs']==source_inputs(current['inputs'])
with Simulator() as sim:
    backend=ROOT/'rtl/backend/rv_backend.sv';text=backend.read_text(encoding='utf-8')
    anchor='direct_wake_data[DIRECT_BYPASS_PORTS]  = system_wake_data_q;'
    assert text.count(anchor)==1
    mutant=folder/'zero_system_wake.sv'
    mutant.write_text(text.replace(anchor,"direct_wake_data[DIRECT_BYPASS_PORTS]  = '0;"),encoding='utf-8')
    files=(ROOT/'rtl/filelist.f').read_text().splitlines()+[
        'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
    files=[mutant.relative_to(ROOT).as_posix() if p=='rtl/backend/rv_backend.sv' else p for p in files]
    cache=folder/'model.json'
    model=json.loads(cache.read_bytes()) if cache.exists() else None
    if not model or model['inputs']!=source_inputs(files) or model['params']!=current['params'] or sha(ROOT/model['binary'])!=model['binary_sha256']:
        model=sim.build('rv23_vector_zero_system_wake','rv32_program_tb',files,current['params'])
        dump(cache,model)
    kind='isolated_zero_data_mutant'
    run,log=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        '+quiet_commit','+htif','+timeout_cycles=100000','+expected_exit_code=0'],
        folder/'simulation.log',120,expected_failure='g_lsu_base_cache_contract')
assert current['inputs']==source_inputs(current['inputs']) and sha(elf)==positive['elf_sha256']
dump(folder/'report.json',dict(passed=True,expected_failure=True,scope='Same native ELF must catch a zero-data system wakeup feeding an IQ load-base cache',
    driver_sha256=sha(__file__),positive_report_sha256=sha(positive_path),kind=kind,
    model=model,run=run,elf_sha256=sha(elf),production_backend_sha256=sha(ROOT/'rtl/backend/rv_backend.sv')))
print('PASS zero-data system wakeup rejected by the same native overlap ELF',kind,flush=True)

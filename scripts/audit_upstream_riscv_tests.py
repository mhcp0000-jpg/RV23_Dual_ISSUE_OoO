"""Bind the full upstream regression to current RTL, test sources and artifacts."""
import json
from sim_runner import ROOT,sha,dump,source_inputs

folder=ROOT/'out/rva23/upstream_riscv_tests'
path=folder/'report.json';report=json.loads(path.read_text(encoding='utf-8'))
assert report['passed']
assert report['pins']=={'tests':'3df703cd52d5f0d8224e3c50bf03c6cb70efff98','env':'6de71edb142be36319e380ce782c3d1830c65d68'}
files=(ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()+[
    'tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
    'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp']
assert report['model']['inputs']==source_inputs(files)
assert '-GHAS_H=1' in report['model']['params'] and '-GXLEN=64' in report['model']['params']
assert sha(ROOT/report['model']['binary'])==report['model']['binary_sha256']
for p,h in report['inputs'].items():assert sha(ROOT/p)==h,p
for phase in ['compile','build']:
    r=report['model'][phase];assert r['passed'] and r['exit_code']==0
    assert sha(ROOT/r['log'])==r['log_sha256']
selected=report['selected']
assert len(selected)==len(set(selected)) and len(selected)==152
assert sorted(row['name'] for row in report['cases'])==sorted(selected)
for row in report['cases']:
    assert row['passed'] and row['inputs']==report['inputs']
    assert row['binary_sha256']==report['model']['binary_sha256']
    for artifact in ['elf','trace']:assert sha(ROOT/row[artifact])==row[artifact+'_sha256']
    for phase in ['compile','run']:
        r=row[phase];assert r['passed'] and r['exit_code']==0
        assert sha(ROOT/r['log'])==r['log_sha256']
    text=(ROOT/row['run']['log']).read_text(encoding='utf-8')
    assert 'PASS rv32_program_tb' in text and 'ELF AXI readback PASS total=' in text and 'data=0x00000001' in text
dump(ROOT/'out/rva23/upstream_isa_evidence.json',dict(passed=True,
    scope='152 pinned upstream self-checking RV64 instruction tests on one current H-enabled SoC; not ACT4 certification or differential validation',
    report_sha256=sha(path),audit_sha256=sha(__file__),source_inputs=report['model']['inputs'],
    binary_sha256=report['model']['binary_sha256'],pins=report['pins'],tests=selected))
print('PASS 152 upstream ISA tests: current RTL, pinned sources, native binary, ELF, trace and logs bound',flush=True)

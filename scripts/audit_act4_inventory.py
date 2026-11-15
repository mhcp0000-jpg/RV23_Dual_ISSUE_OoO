# SPDX-License-Identifier: Apache-2.0
"""Record official ACT selection, exclusions, source hashes, and execution gaps."""
import json, subprocess
from collections import Counter
from pathlib import Path
from act.parse_test_constraints import generate_test_dict
from act.parse_udb_config import get_config_params, get_implemented_extensions
from act.select_tests import select_tests, check_test_extensions, check_test_params
from sim_runner import ROOT, sha, dump

vendor=ROOT/'third_party/riscv-arch-test'
cfg=ROOT/'config/act4/rv23/rv23.yaml'
work=ROOT/'out/act4/work/rv23-RVA23S64'
all_tests=generate_test_dict(vendor/'tests','all')
params=get_config_params(cfg)
extensions=get_implemented_extensions(work/'extensions.txt')
selected=select_tests(all_tests,extensions,params)
items={}
for name,meta in all_tests.items():
    chosen=name in selected
    elf=work/'elfs'/Path(name).with_suffix('.elf')
    source=meta.test_path
    items[name]=dict(selected=chosen,
        reason='selected' if chosen else ('extension constraints' if not check_test_extensions(
            meta.required_extensions,meta.forbidden_extensions,extensions) else 'parameter constraints'),
        requirements=[requirement if isinstance(requirement,str) else sorted(requirement)
                      for requirement in meta.required_extensions],
        params=meta.params,source=source.relative_to(ROOT).as_posix(),source_sha256=sha(source),
        elf=elf.relative_to(ROOT).as_posix() if elf.exists() else None,
        elf_sha256=sha(elf) if elf.exists() else None)
required=set()
for meta in selected.values():
    for requirement in meta.required_extensions:
        required.update([requirement] if isinstance(requirement,str) else requirement)
results={}
for results_path in (ROOT/'out/act4/dut').glob('results*.json'):
    data=json.loads(results_path.read_text(encoding='utf-8'))
    results.update(data.get('results',{}))
report=dict(scope='ACT4 inventory and RTL results; not complete profile certification',
    act_commit=subprocess.check_output(['git','-C',str(vendor),'rev-parse','HEAD'],text=True).strip(),
    official_required_sail='0.13.1',actual_sail='0.16',
    reference_version_exception='Official 0.13.1 fixes hartSupports(Ext_H)=false; 0.16 supports H. Framework version requirement explicitly overridden, version output is genuine.',
    configuration_sha256=sha(cfg),candidates=len(all_tests),selected=len(selected),
    built=sum(items[name]['elf'] is not None for name in selected),
    suites=dict(sorted(Counter(meta.coverage_group for meta in selected.values()).items())),
    configured_extensions_without_explicit_selected_requirement=sorted(extensions-required),
    rtl_executed=len(results),rtl_passed=sum(r['passed'] for r in results.values()),
    rtl_failed=sum(not r['passed'] for r in results.values()),
    tests=items)
dump(ROOT/'out/act4/inventory.json',report)
print(json.dumps({key:value for key,value in report.items() if key!='tests'},indent=2),flush=True)

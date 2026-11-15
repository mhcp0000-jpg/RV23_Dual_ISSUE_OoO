# SPDX-License-Identifier: Apache-2.0
"""Aggregate ACT4 execution evidence against current tests, ELFs and RTL."""
import argparse, hashlib, json, re, subprocess
from collections import Counter
from pathlib import Path
from sim_runner import ROOT, sha, dump

folder=ROOT/'out/act4'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--current',action='store_true',help='Audit the current checked-in and generated-vector results')
args=parser.parse_args()
inventory=json.loads((folder/'inventory.json').read_text(encoding='utf-8'))
model_path=folder/'dut/model.json'
model=json.loads(model_path.read_text(encoding='utf-8'))
assert sha(ROOT/model['binary'])==model['binary_sha256']
for path,digest in model['inputs'].items():assert sha(ROOT/path)==digest,path
elfs=folder/'work/rv23-RVA23S64/elfs'
checked_in_metadata={Path(name).with_suffix('.elf').as_posix():item
                     for name,item in inventory['tests'].items() if item['selected']}
checked_in=set(checked_in_metadata)
generated={p.relative_to(elfs).as_posix() for p in elfs.rglob('*.elf')
           if re.fullmatch(r'(?:Vx|Vls)(?:8|16|32|64)|Vf(?:32|64)|Zvfhmin',p.parent.name)} if args.current else set()
selected=checked_in | generated
reports={}
combined={}
generated_hashes={}
if args.current:
    assert len(checked_in)==663 and len(generated)==2083 and not checked_in & generated
    vector_pin = json.loads((ROOT/'config/act4/rv23/vector_elf_set.json').read_text(encoding='utf-8'))
    assert vector_pin['act_commit'] == inventory['act_commit'] and vector_pin['count'] == len(generated)
    generated_hashes = {name: sha(elfs/name) for name in sorted(generated)}
    canonical = json.dumps(generated_hashes, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    vector_elf_set_sha256 = hashlib.sha256(canonical.encode('ascii')).hexdigest()
    assert vector_elf_set_sha256 == vector_pin['vector_elf_set_sha256'], 'Generated vector ELF set changed'
    paths={folder/'dut/current-checked-in.json':checked_in,folder/'dut/current-vector.json':generated}
else:
    paths=dict.fromkeys((folder/'dut').glob('results*.json'))
for path,expected in paths.items():
    report=json.loads(path.read_text(encoding='utf-8'))
    assert report['binary_sha256']==model['binary_sha256'],str(path)
    if args.current:
        assert report['model_sha256']==sha(model_path) and report['act_commit']==inventory['act_commit']
        assert set(report['selected'])==expected and set(report['results'])<=expected
    reports[path.name]=dict(sha256=sha(path),passed=sum(r['passed'] for r in report['results'].values()))
    for name,result in report['results'].items():
        if name in combined:assert result==combined[name],name
        elf=folder/'work/rv23-RVA23S64/elfs'/name
        elf_hash = generated_hashes[name] if name in generated_hashes else sha(elf)
        assert elf_hash == result['elf_sha256'], name
        if args.current and name in checked_in_metadata:
            assert result['elf_sha256']==checked_in_metadata[name]['elf_sha256'],('ELF changed since inventory',name)
        log=ROOT/result['log'];assert sha(log)==result['log_sha256'],name
        text=log.read_text(encoding='utf-8',errors='replace')
        if result['passed']:
            assert result['exit_code']==0 and not result['timed_out'],name
            assert re.search(r'RVCP-SUMMARY: TEST PASSED - Test File "[^"]+"',text),name
            assert 'RVCP-SUMMARY: TEST FAILED' not in text,name
            assert 'PASS rv_act4_program_tb' in text,name
        combined[name]=result
for repo in ['riscv-arch-test','sail-riscv','sail-riscv-act4']:
    changed=subprocess.check_output(['git','-C',str(ROOT/'third_party'/repo),'status','--porcelain'],text=True).strip()
    assert not changed,(repo,changed)
assert set(combined)<=selected,set(combined)-selected
missing=sorted(selected-set(combined));failures={name:result for name,result in combined.items() if not result['passed']}
negative=ROOT/'out/negative_controls'/('act4_add_sub_current' if args.current else 'act4_add_sub')/'report.json'
neg=json.loads(negative.read_text(encoding='utf-8')) if negative.exists() else None
if neg:
    assert neg['passed'] and neg['binary_sha256']==model['binary_sha256']
    assert sha(ROOT/neg['original'])==neg['original_sha256']
    assert sha(ROOT/neg['mutant'])==neg['mutant_sha256']
    assert sha(ROOT/neg['log'])==neg['log_sha256']
report=dict(scope='Content-bound official ACT4 test execution with explicit Sail 0.16 compatibility exception',
    full_profile_verified=False,official_act4_reference_pin_satisfied=False,
    required_sail='0.13.1',actual_sail='0.16',act_commit=inventory['act_commit'],
    selected=len(selected),executed=len(combined),passed=len(combined)-len(failures),failed=len(failures),
    pending=len(missing),all_selected_passed=not missing and not failures,
    binary_sha256=model['binary_sha256'],inventory_sha256=sha(folder/'inventory.json'),
    model_sha256=sha(model_path),reports=reports,
    negative_control_passed=bool(neg and neg['passed']),
    reference_driver_sha256=sha(folder/'sail-0.16/sail_act4_reference.exe'),
    tests_without_results=missing,failures=failures,
    limitations=['Required Sail 0.13.1 cannot model H; genuine official 0.16 used explicitly',
                 ('Checked-in suites have no explicit V/H requirements; generated V is separately tested and H uses directed evidence' if args.current else
                  'Selected ACT4 suites contain no explicit V/H requirements'),
                 'Full normative-clause, timing and concurrent memory-agent coverage remains separate'])
if args.current:
    report['vector_elf_set_sha256'] = vector_elf_set_sha256
    exact_requirements = Counter(requirement for name in checked_in if combined.get(name, {}).get('passed')
        for requirement in checked_in_metadata[name]['requirements']
        if isinstance(requirement, str))
    report['passed_checked_in_exact_requirements'] = dict(sorted(exact_requirements.items()))
    report['passed_generated_vector_suites'] = dict(sorted(Counter(
        Path(name).parent.name for name in generated if combined.get(name, {}).get('passed')).items()))
dump(folder/('current_execution_audit.json' if args.current else 'verification_report.json'),report)
print(json.dumps({k:v for k,v in report.items() if k not in ['tests_without_results','failures']},indent=2),flush=True)

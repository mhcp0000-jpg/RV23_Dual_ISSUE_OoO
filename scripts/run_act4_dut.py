# SPDX-License-Identifier: Apache-2.0
"""Execute official self-checking ACT4 ELFs on the content-bound RTL model."""
import argparse
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sim_runner import ROOT, dump, sha

parser = argparse.ArgumentParser()
parser.add_argument('--suite', default='')
parser.add_argument('--exclude-suite', default='')
parser.add_argument('--report', default='results.json')
parser.add_argument('--cycles', type=int, default=20000000)
parser.add_argument('--timeout', type=int, default=600)
parser.add_argument('--rerun', action='store_true')
parser.add_argument('--workers', type=int, default=8)
parser.add_argument('--elf-verify', type=int, choices=[0,1], default=0)
parser.add_argument('--sample-first-per-suite', action='store_true')
parser.add_argument('--elf-root', default='out/act4/work/rv23-RVA23S64/elfs')
parser.add_argument('--act-source-root', default='third_party/riscv-arch-test',
                    help='ACT checkout used to generate the ELFs')
coverage = parser.add_mutually_exclusive_group()
coverage.add_argument('--vector-only', action='store_true')
coverage.add_argument('--inventory-selected', action='store_true',
                      help='Run the checked-in ELFs selected in the profile inventory')
parser.add_argument('--min-elf-age',type=float,default=0)
args = parser.parse_args()
folder = ROOT / 'out/act4/dut'
model_path = folder / 'model.json'
model = json.loads(model_path.read_text(encoding='utf-8'))
assert model['passed']
binary = ROOT / model['binary']
assert sha(binary) == model['binary_sha256']
for name, digest in model['inputs'].items():
    assert sha(ROOT / name) == digest, name
elf_root = ROOT / args.elf_root
elfs = sorted(elf_root.rglob('*.elf'))
if args.inventory_selected:
    inventory = json.loads((folder.parent / 'inventory.json').read_text(encoding='utf-8'))
    selected = {Path(name).with_suffix('.elf').as_posix()
                for name, entry in inventory['tests'].items() if entry['selected']}
    elfs = [elf for elf in elfs if elf.relative_to(elf_root).as_posix() in selected]
    missing = selected - {elf.relative_to(elf_root).as_posix() for elf in elfs}
    assert not missing, f'Missing inventory-selected ELFs: {sorted(missing)}'
if args.min_elf_age:
    elfs=[p for p in elfs if time.time()-p.stat().st_mtime>=args.min_elf_age]
if args.vector_only:
    elfs=[p for p in elfs if re.fullmatch(r'(?:Vx|Vls)(?:8|16|32|64)|Vf(?:32|64)|Zvfhmin',p.parent.name)]
if args.suite:
    elfs = [p for p in elfs if args.suite in p.relative_to(elf_root).parts]
if args.exclude_suite:
    elfs = [p for p in elfs if args.exclude_suite not in p.relative_to(elf_root).parts]
if args.sample_first_per_suite:
    first={}
    for elf in elfs:first.setdefault(elf.parent.relative_to(elf_root).as_posix(),elf)
    elfs=list(first.values())
assert elfs, 'No self-checking ACT4 ELFs found'
report_path = folder / args.report
old = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
model_digest = sha(model_path)
act_commit = subprocess.check_output(['git','-C',str(ROOT / args.act_source_root),
                                      'rev-parse','HEAD'],text=True).strip()
if args.inventory_selected:
    assert act_commit == inventory['act_commit'], 'ACT checkout differs from the selected inventory'
same_run_inputs = (old.get('binary_sha256') == model['binary_sha256'] and
                   old.get('model_sha256') == model_digest and old.get('act_commit') == act_commit)
previous_results = old.get('results', {}) if same_run_inputs and not args.rerun else {}
results = {}
report = dict(scope='Official ACT4 self-checking ELF execution on RTL; test passes alone do not certify a profile',
              binary_sha256=model['binary_sha256'], model_sha256=model_digest, act_commit=act_commit,
              selected=[p.relative_to(elf_root).as_posix() for p in elfs], results=results)
env = os.environ.copy()


def save_report():
    passed = sum(result['passed'] for result in results.values())
    report.update(executed=len(results), passed=passed, failed=len(results)-passed)
    temp = report_path.with_name(f'{report_path.name}.{os.getpid()}.tmp')
    dump(temp, report)
    # On Windows, readers and scanners can briefly deny replacement of a
    # closed file. Keep the last complete report visible while retrying.
    deadline = time.monotonic() + 5
    while True:
        try:
            temp.replace(report_path)
            return
        except PermissionError as error:
            if getattr(error, 'winerror', None) not in (5, 32) or time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


def execute(elf):
    name = elf.relative_to(elf_root).as_posix()
    digest = sha(elf)
    log_root='logs' if args.report=='results.json' else 'logs-'+Path(args.report).stem
    log = folder / log_root / (name + '.log')
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [str(binary), '+elf=' + str(elf), '+quiet_commit',
               '+timeout_cycles=' + str(args.cycles), '+expected_exit_code=0',
               '+elf_verify=' + str(args.elf_verify)]
    started = time.monotonic()
    timed_out = False
    with log.open('w', encoding='utf-8') as stream:
        try:
            proc = subprocess.run(command, cwd=ROOT, env=env, stdout=stream,
                                  stderr=subprocess.STDOUT, timeout=args.timeout)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            code = None
    output = log.read_text(encoding='utf-8', errors='replace')
    witnesses = re.findall(r'RVCP-SUMMARY: TEST PASSED - Test File "[^"]+"', output)
    failed = 'RVCP-SUMMARY: TEST FAILED' in output
    passed = code == 0 and bool(witnesses) and not failed and 'PASS rv_act4_program_tb' in output
    result = dict(passed=passed, elf_sha256=digest, exit_code=code, timed_out=timed_out,
                         seconds=round(time.monotonic()-started,3), witnesses=witnesses,
                         log=log.relative_to(ROOT).as_posix(), log_sha256=sha(log), command=command)
    return name,result,output

pending=[]
for elf in elfs:
    name=elf.relative_to(elf_root).as_posix()
    previous=previous_results.get(name,{})
    log=ROOT/previous.get('log','missing')
    if (previous.get('passed') and previous.get('exit_code') == 0 and not previous.get('timed_out')
            and previous.get('elf_sha256')==sha(elf)
            and log.is_file() and previous.get('log_sha256')==sha(log)):
        results[name] = previous
        print(f'CACHED {name}: PASS',flush=True)
    else:pending.append(elf)
with ThreadPoolExecutor(max_workers=args.workers) as pool:
    futures=[pool.submit(execute,elf) for elf in pending]
    for index,future in enumerate(as_completed(futures),1):
        name,result,output=future.result()
        results[name]=result
        save_report()
        print(f'{"PASS" if result["passed"] else "FAIL"} {index}/{len(pending)} {name} '
              f'{result["seconds"]}s',flush=True)
        if not result['passed']:print(output[-3500:],flush=True)
for name, digest in model['inputs'].items():
    assert sha(ROOT / name) == digest, 'RTL changed during execution: ' + name
assert sha(binary) == model['binary_sha256']
save_report()
print(f'ACT4 RTL: {report.get("passed",0)} passed, {report.get("failed",0)} failed', flush=True)
raise SystemExit(0 if all(results[p.relative_to(elf_root).as_posix()]['passed'] for p in elfs) else 1)

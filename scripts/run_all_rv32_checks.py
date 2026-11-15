"""One entry point for the full RV32 verification contract and final audit."""
import argparse,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--update-manifest',action='store_true')
parser.add_argument('--resume',action='store_true',help='Reuse gates only if the complete current release audit succeeds')
args=parser.parse_args()
steps=[['check_manifest.py']+(['--update'] if args.update_manifest else []),
       ['run_regression.py','--resume'],['run_bus_lock_checks.py'],
       ['run_sequence_negative.py'],['check_cache_word_lock_negative.py'],
       ['check_cache_launch_negative.py'],['run_extended.py'],
       ['run_programs.py','--resume'],['compare_banked_performance.py'],
       ['check_banked_control_trace.py'],['check_write_path_performance.py'],
       ['profile_memory_paths.py','--label','after']]
if (ROOT/'out/performance/tim_reference_elf/report.json').exists():
    steps.append(['run_preserved_tim_elf.py'])
steps += [['audit_rv32_release.py'],
       ['save_verification_snapshot.py']]
if args.resume:
    # The audit checks every gate's source, TB, executable, runtime and log
    # hashes. A stale/missing/failed gate falls back to the full workflow.
    current=subprocess.run([sys.executable,str(ROOT/'scripts/audit_rv32_release.py')],cwd=ROOT)
    if current.returncode==0:
        print('REUSE all source-bound RV32 release gates; refresh publication probes',flush=True)
        steps=[step for step in steps if step[0] in {
            'check_manifest.py','profile_memory_paths.py','run_preserved_tim_elf.py',
            'audit_rv32_release.py','save_verification_snapshot.py'}]
for step in steps:
    print('RUN',*step,flush=True)
    subprocess.run([sys.executable,str(ROOT/'scripts'/step[0]),*step[1:]],cwd=ROOT,check=True)
print('PASS complete RV32 verification contract',flush=True)

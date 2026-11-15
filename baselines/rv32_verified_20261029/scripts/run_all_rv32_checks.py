"""One entry point for the full RV32 verification contract and final audit."""
import argparse,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--update-manifest',action='store_true')
args=parser.parse_args()
steps=[['check_manifest.py']+(['--update'] if args.update_manifest else []),
       ['run_regression.py','--resume'],['run_bus_lock_checks.py'],
       ['run_sequence_negative.py'],['check_cache_word_lock_negative.py'],
       ['check_cache_launch_negative.py'],['run_extended.py'],
       ['run_programs.py','--resume'],['compare_banked_performance.py'],
       ['check_banked_control_trace.py'],['check_write_path_performance.py'],['audit_rv32_release.py'],
       ['save_verification_snapshot.py']]
for step in steps:
    print('RUN',*step,flush=True)
    subprocess.run([sys.executable,str(ROOT/'scripts'/step[0]),*step[1:]],cwd=ROOT,check=True)
print('PASS complete RV32 verification contract',flush=True)

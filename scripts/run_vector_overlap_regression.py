"""Focused overlap regression; requires the documented Sail event-model setup."""
import subprocess,sys
from sim_runner import ROOT

steps=['run_hypervisor_integration.py','run_vector_scalar_overlap.py',
       'run_vector_scalar_irq.py','check_vector_system_wake_negative.py',
       'audit_vector_scalar_overlap.py']
for name in steps:
    print('RUN',name,flush=True)
    subprocess.run([sys.executable,str(ROOT/'scripts'/name)],cwd=ROOT,check=True)
print('PASS focused scalar/vector overlap regression; full-profile release gates remain separate',flush=True)

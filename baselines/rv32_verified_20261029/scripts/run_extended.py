"""Current RV32 baseline plus three independently seeded system scoreboards."""
import json,subprocess,sys
from sim_runner import ROOT,Simulator,sha,dump

subprocess.run([sys.executable,str(ROOT/'scripts/run_checks.py')],cwd=ROOT,check=True)
baseline=json.loads((ROOT/'out/verification.json').read_text())
assert baseline['passed']
report={'passed':False,'baseline':baseline,'seeds':[],
        'scope':'RV32 core baseline, 32KiB cache capacity/error tests, seeded shared-SRAM I/D scoreboard'}
path=ROOT/'out/extended.json';dump(path,report)
with Simulator() as sim:
    for seed in [1,305419896,3735928559]:
        result,text=sim.run([ROOT/'out/rv23_memory_tb/Vrv23_memory_tb.exe',
            '+random_mem',f'+seed={seed}'],ROOT/f'out/random_memory_seed_{seed}.log',120)
        assert 'RANDOM MEMORY PASS transactions=1024' in text
        assert 'PASS rv23_memory_tb' in text
        report['seeds'].append({'seed':seed,'passed':True,'run':result,
            'test_sha256':sha(ROOT/'tb/rv23_memory_tb.sv'),
            'binary_sha256':sha(ROOT/'out/rv23_memory_tb/Vrv23_memory_tb.exe')})
        print('PASS random shared SRAM scoreboard seed',seed,flush=True);dump(path,report)
report['passed']=True;dump(path,report)

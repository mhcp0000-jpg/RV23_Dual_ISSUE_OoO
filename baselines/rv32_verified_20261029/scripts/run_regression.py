from pathlib import Path
import argparse,json,sys
from sim_runner import ROOT,Simulator,sha,dump

ap=argparse.ArgumentParser()
ap.add_argument('--only',nargs='+')
ap.add_argument('--resume',action='store_true')
args=ap.parse_args()
manifest=json.loads((ROOT/'config/regression.json').read_text())
cases=manifest['cases']
if args.only:cases=[c for c in cases if c['name'] in args.only or c['top'] in args.only]
if not cases:raise SystemExit('No selected regression cases')
path=ROOT/'out/regression/report.json'
previous=json.loads(path.read_text()) if args.resume and path.exists() else {}
done={r['name']:r for r in previous.get('cases',[]) if r.get('passed')}
report={'passed':False,'state':'running','target':'RV32IMFC_Zicsr_Zifencei',
        'expected_cases':[c['name'] for c in cases],'cases':[],
        'excluded':manifest['excluded'],
        'scope':'Original reusable block/backend tests; finite simulation, not full ISA/STA'}
with Simulator() as sim:
    fp_vectors='out/regression/fpu_vectors.hex'
    if any(c['top']=='rv_fpu_diff_tb' for c in cases):
        sim.run([sys.executable,'scripts/gen_fpu_diff_vectors.py','--corners',
            '--seed','0x20260910','--random-per-op-rm','1024','--output',fp_vectors],
            ROOT/'out/regression/fpu_generate.log',120)
    for index,case in enumerate(cases):
        name=case['name']
        current={p:sha(ROOT/p) for p in case['files']}
        runtime_inputs={}
        if case['top']=='rv_fpu_diff_tb':
            runtime_inputs={fp_vectors:sha(ROOT/fp_vectors),
                'scripts/gen_fpu_diff_vectors.py':sha(ROOT/'scripts/gen_fpu_diff_vectors.py')}
        if case['top']=='rv_soc_peripheral_tb':
            fixture='tb/fixtures/bootrom/bootrom_test.hex'
            runtime_inputs={fixture:sha(ROOT/fixture)}
        current.update(runtime_inputs)
        old=done.get(name)
        if old and old['inputs']==current and old['params']==case['params'] and \
            (ROOT/old['binary']).exists() and sha(ROOT/old['binary'])==old['binary_sha256']:
            report['cases'].append(old);print('REUSE bound PASS',name,flush=True)
            dump(path,report);continue
        print(f'RUN {index+1}/{len(cases)} {name}',flush=True)
        try:
            record=sim.build(name,case['top'],case['files'],case['params'])
            record['inputs'].update(runtime_inputs)
            if case['top']=='rv_fpu_diff_tb':
                record['vector_sha256']=sha(ROOT/fp_vectors)
                record['runs']=[sim.simulate(record,[f'+fpu_vectors={fp_vectors}'],label='static'),
                    sim.simulate(record,[f'+fpu_vectors={fp_vectors}','+fpu_dynamic_rm'],label='dynamic')]
                text=(ROOT/fp_vectors).read_text().splitlines()
                fields=text[0].split();fields[5]=f'{int(fields[5],16)^1:08x}';text[0]=' '.join(fields)
                mutant=ROOT/'out/regression/fpu_wrong_expected.hex'
                mutant.write_text('\n'.join(text)+'\n')
                record['oracle_negative_control']=sim.simulate(record,
                    ['+fpu_vectors=out/regression/fpu_wrong_expected.hex'],label='wrong_expected',
                    expected_failure='FPU differential mismatch')
            else:record['runs']=[sim.simulate(record)]
            record['passed']=True
            print('PASS',name,flush=True)
        except Exception as error:
            record={'name':name,'passed':False,'failure':str(error),'inputs':current}
            print('FAIL',name,str(error)[-3000:],flush=True)
        report['cases'].append(record);dump(path,report)
report['state']='finished'
report['passed']=len(report['cases'])==len(cases) and all(c['passed'] for c in report['cases'])
dump(path,report)
print('REGRESSION',sum(c['passed'] for c in report['cases']),'/',len(cases),flush=True)
sys.exit(not report['passed'])

"""Verify stable ACT DUT manifests and rejection of a corrupted smoke log."""
import json,sys
from sim_runner import ROOT,Simulator,sha,dump,source_inputs

folder=ROOT/'out/act4/dut';path=folder/'model.json'
before=json.loads(path.read_bytes());assert before['passed']
assert before['inputs']==source_inputs(before['inputs'])
assert sha(ROOT/before['binary'])==before['binary_sha256']
manifest_before=sha(path);steps=[]
with Simulator() as sim:
    record,text=sim.run([sys.executable,'scripts/build_act4_dut.py'],folder/'cache_test_before.log',120)
    assert 'source-bound cached result' in text and sha(path)==manifest_before
    steps.append(record)
    log=ROOT/before['smoke']['log'];original=log.read_bytes()
    assert sha(log)==before['smoke']['log_sha256']
    suffix=b'\nCACHE_INVALIDATION_PROBE\n';log.write_bytes(original+suffix)
    try:
        record,text=sim.run([sys.executable,'scripts/build_act4_dut.py'],folder/'cache_test_replay.log',120)
        assert 'PASS full H/V ACT4 DUT harness smoke' in text and 'cached result' not in text
        steps.append(record)
    finally:
        if log.read_bytes().endswith(suffix):log.write_bytes(original)
    after=json.loads(path.read_bytes())
    assert after['passed'] and after['inputs']==before['inputs'] and after['params']==before['params']
    assert after['binary_sha256']==before['binary_sha256']
    assert after['compile']==before['compile'] and after['build']==before['build']
    assert after['smoke_inputs']==before['smoke_inputs']
    assert sha(ROOT/after['smoke']['log'])==after['smoke']['log_sha256']
    manifest_after=sha(path)
    record,text=sim.run([sys.executable,'scripts/build_act4_dut.py'],folder/'cache_test_after.log',120)
    assert 'source-bound cached result' in text and sha(path)==manifest_after
    steps.append(record)
dump(folder/'cache_checks.json',dict(passed=True,complete_profile_validation=False,
    scope='ACT DUT cache metadata: unchanged manifests stay byte-identical; a corrupted smoke log forces replay using the same compiled model. Not the ACT suite.',
    driver_sha256=sha(__file__),builder_sha256=sha(ROOT/'scripts/build_act4_dut.py'),
    manifest_before=manifest_before,manifest_after=manifest_after,
    binary_sha256=after['binary_sha256'],smoke_inputs=after['smoke_inputs'],
    model_inputs=after['inputs'],steps=steps,corrupted_log_controls=1))
print('PASS stable ACT DUT manifest and stale-log invalidation/replay',flush=True)

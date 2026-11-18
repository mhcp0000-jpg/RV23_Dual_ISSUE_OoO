"""Record current RV64 arithmetic-unit request/result handshake latencies."""
import json
import re

from sim_runner import ROOT, Simulator, dump, sha, source_inputs


def main():
    folder = ROOT / 'out/performance/pipeline_latency'
    folder.mkdir(parents=True, exist_ok=True)
    provenance = json.loads((ROOT / 'rtl/vendor/hardfloat/PROVENANCE.json').read_bytes())
    files = ['rtl/rv_ooo_pkg.sv', 'rtl/backend/rv_fp_decode_pkg.sv'] + [
        item['path'] for item in provenance['files'] if item['path'].endswith('.v')] + [
        'rtl/backend/rv_fp_format.sv', 'rtl/backend/rv_fp_convert.sv', 'rtl/backend/rv_fp_round_to_int.sv',
        'rtl/backend/rv_fp_immediate.sv', 'rtl/backend/rv_fp_cvtmod.sv', 'rtl/backend/rv_fpu_rva23.sv',
        'rtl/backend/rv_multiplier.sv', 'rtl/backend/rv_divider.sv', 'tb/unit/backend/rv_pipeline_latency_tb.sv']
    headers = [item['path'] for item in provenance['files'] if item['path'].endswith('.vi')]
    with Simulator() as sim:
        prior = folder / 'report.json'
        model = json.loads(prior.read_bytes())['model'] if prior.exists() else None
        if not model or model['inputs'] != source_inputs(files, headers) or sha(ROOT / model['binary']) != model['binary_sha256']:
            model = sim.build('rv64_pipeline_latency', 'rv_pipeline_latency_tb', files, dependencies=headers)
        run, log = sim.run([ROOT / model['binary']], folder / 'simulation.log', 120)
    measured = {name: int(cycles) for name, cycles in re.findall(r'^PIPE_LAT (\w+) cycles=(\d+)$', log, re.M)}
    assert len(measured) == 19 and 'PASS pipeline unit latency' in log
    assert measured['MUL'] == measured['MULW'] == 2
    assert measured['DIVU'] == 65 and measured['DIVUW'] == 33
    assert measured['DIV_zero'] == measured['DIV_overflow'] == 1
    assert all(measured[name] == 2 for name in ('FADD_S', 'FADD_D', 'FMUL_S', 'FMUL_D', 'FMADD_S', 'FMADD_D', 'FCVT_S_W'))
    assert source_inputs(model['inputs']) == model['inputs']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    dump(folder / 'report.json', dict(passed=True, driver_sha256=sha(__file__),
        scope='Unit acceptance edge to result handoff edge, result_ready=1, no flush; slow FP values are named samples, not universal latency bounds',
        model=model, run=run, cycles=measured))
    configuration = source_inputs(['rtl/rv_ooo_pkg.sv', 'rtl/rv_ooo_core.sv', 'rtl/backend/rv_backend.sv',
        'rtl/frontend/rv_frontend.sv', 'rtl/frontend/rv_fetch_queue.sv', 'rtl/backend/rv_issue_queue.sv',
        'rtl/backend/rv_exec_result_buffer.sv', 'rtl/backend/rv_rob.sv'])
    dump(ROOT / 'docs/evidence/pipeline_latency.json', dict(passed=True,
        scope='Measured unit acceptance/result handshakes, not a physical whole-core pipeline-depth or Fmax measurement; slow FP latencies are named examples',
        driver_sha256=sha(__file__), rtl_and_tb_inputs=model['inputs'],
        integration_source_inputs=configuration, binary_sha256=model['binary_sha256'], run=run,
        cycles=measured, source_report_sha256=sha(folder / 'report.json')))
    print('PASS measured RV64 unit latency', measured)


if __name__ == '__main__':
    main()

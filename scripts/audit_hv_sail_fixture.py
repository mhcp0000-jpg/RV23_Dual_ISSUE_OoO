"""Recheck saved run_hv_sail_fixture artifacts without rebuilding its ELF."""
import json

from sim_runner import ROOT, sha, source_inputs


def check_fixture(folder, generator, generated_text, verify_traces):
    report = json.loads((folder / 'report.json').read_bytes())
    assert report['passed'] and report['generator_sha256'] == sha(generator)
    assert (folder / 'test.S').read_text(encoding='utf-8') == generated_text
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(report['model']['params'])
    assert source_inputs(report['model']['inputs']) == report['model']['inputs']
    assert source_inputs(report['runtime_inputs']) == report['runtime_inputs']
    assert sha(ROOT / report['model']['binary']) == report['model']['binary_sha256']
    for filename, key in [('test.S', 'source_sha256'), ('test.elf', 'elf_sha256'),
                          ('commit.csv', 'trace_sha256'), ('sail.csv', 'sail_trace_sha256')]:
        assert sha(folder / filename) == report[key]
    for key in ('compile', 'run', 'sail'):
        step = report[key]
        assert step['passed'] and step['exit_code'] == 0 and sha(ROOT / step['log']) == step['log_sha256']
    outcomes = verify_traces(folder / 'sail.csv', folder / 'commit.csv')
    assert outcomes == report['outcomes']
    return outcomes

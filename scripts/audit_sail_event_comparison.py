"""Recheck event-complete privileged comparison and omitted-event controls."""
import json

from sim_runner import ROOT, dump, sha
from run_sail_event_comparison import compare, read_csv


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def execution(run):
    assert run['passed'] and run['exit_code'] == 0
    assert sha(ROOT / run['log']) == run['log_sha256']


def verify_reference_driver():
    driver_path = ROOT / 'out/reference/sail-event-driver/report.json'
    driver = read(driver_path)
    assert driver['passed'] and driver['generator_sha256'] == sha(ROOT / 'scripts/build_sail_event_driver.py')
    reference_path = ROOT / 'out/reference/sail-riscv-0.16-cygwin/build_report.json'
    assert driver['base_report_sha256'] == sha(reference_path)
    reference = read(reference_path)
    for model in (driver, reference):
        assert sha(ROOT / model['binary']) == model['binary_sha256']
    for inputs in (driver['inputs'], reference['host_runtime_sha256']):
        for path, digest in inputs.items():
            assert sha(ROOT / path) == digest, path
    for path, digest in reference['generated_inputs'].items():
        assert sha(reference_path.parent / 'build' / path) == digest
    generated = ROOT / 'out/reference/sail-event-driver/sail_bounded_driver.cpp'
    assert sha(generated) == driver['generated_driver_sha256']
    original = (ROOT / 'scripts/reference/sail_bounded_driver.cpp').read_text(encoding='utf-8')
    assert generated.read_text(encoding='utf-8') == original.replace(
        '#include "sail_trace_callbacks.h"', '#include "sail_trace_events.h"')
    execution(driver['compile'])
    execution(driver['version'])
    return driver


def main():
    folder = ROOT / 'out/rva23/sail_privileged_events'
    report = read(folder / 'report.json')
    assert report['passed'] and not report['complete_profile_validation']
    assert report['generator_sha256'] == sha(ROOT / 'scripts/run_sail_event_comparison.py')
    base_path = ROOT / 'out/rva23/sail_upstream_comparison/report.json'
    assert report['base_report_sha256'] == sha(base_path)
    base = read(base_path)
    assert base['passed']
    driver_path = ROOT / 'out/reference/sail-event-driver/report.json'
    assert report['driver_report_sha256'] == sha(driver_path)
    verify_reference_driver()
    assert sha(ROOT / base['model']['binary']) == base['model']['binary_sha256']
    for path, digest in {**base['inputs'], **base['model']['inputs']}.items():
        assert sha(ROOT / path) == digest, path
    assert report['config_sha256'] == sha(ROOT / 'config/reference/sail-rv23.json')
    expected = {c['name']:c for c in base['cases'] if c['name'].startswith(('rv64mi/', 'rv64si/'))}
    assert len(expected) == len(report['cases']) == 16
    assert {c['name'] for c in report['cases']} == set(expected)
    count = controls = 0
    for case in report['cases']:
        baseline = expected[case['name']]
        assert case['passed'] and baseline['reference_passed'] and baseline['rtl_passed']
        for key in ['elf', 'rtl_trace']:
            assert sha(ROOT / baseline[key]) == baseline[key + '_sha256'] == case[key + '_sha256']
        assert sha(ROOT / case['sail_trace']) == case['sail_trace_sha256']
        execution(case['run'])
        left, right = read_csv(ROOT / case['sail_trace']), read_csv(ROOT / baseline['rtl_trace'])
        compared, mismatch = compare(left, right)
        assert mismatch is None and compared == case['compared']
        assert case['interrupts'] == sum(r['interrupt'] == '1' for r in left)
        assert case['wfi'] == sum(int(r['instruction'], 16) == 0x10500073 for r in left)
        count += compared
        if case['name'] in ['rv64mi/illegal', 'rv64si/wfi']:
            negative = case['omission_control']
            assert negative['rejected']
            assert sha(ROOT / negative['trace']) == negative['trace_sha256']
            omitted = read_csv(ROOT / negative['trace'])
            index = negative['index']
            assert omitted == left[:index] + left[index + 1:]
            if case['name'].endswith('illegal'):
                assert left[index]['interrupt'] == '1' and left[index]['fetched'] == '0'
            else:
                assert int(left[index]['instruction'], 16) == 0x10500073 and left[index]['waiting'] == '1'
            bad_index, bad = compare(omitted, right)
            assert bad is not None and bad_index == index and bad == negative['mismatch']
            controls += 1
    assert count == report['retirements_compared'] == 2554
    assert controls == report['omission_controls'] == 2
    dump(folder / 'audit.json', dict(passed=True, complete_profile_validation=False,
        scope=report['scope'], audit_sha256=sha(__file__), report_sha256=sha(folder / 'report.json'),
        privileged_elfs=16, events_compared=count, omitted_event_controls=controls))
    print('PASS current Sail privileged event audit: 16 ELFs, 2554 events, 2 omission controls')


if __name__ == '__main__':
    main()

"""Bind the upstream RVA23 checked-in selection to Sail and RTL execution."""

import json
import re
from collections import Counter

from run_act4_current_h import REVISION, SAIL_REVISION, SOURCE, git
from sim_runner import ROOT, dump, sha


FOLDER = 'out/act4/current_rva23_inventory'
NAME = 'rv23-RVA23S64-current-inventory'


def read(path):
    return json.loads(path.read_bytes())


def main():
    folder = ROOT / FOLDER
    work = folder / 'work' / NAME
    assert git('rev-parse', 'HEAD') == REVISION
    git('diff', '--exit-code', 'HEAD', '--', 'framework', 'tests', 'uv.lock', 'pyproject.toml')
    framework = ROOT / SOURCE / 'framework/src/act/config.py'
    assert 'REQUIRED_SAIL_VERSION = "0.16"' in framework.read_text(encoding='utf-8')
    selection = read(folder / 'selection_audit.json')
    generation = read(folder / 'generation_audit.json')
    assert selection['upstream_revision'] == REVISION and selection['certificate_filter'] == 'RVA23'
    assert generation['build_passed'] and generation['selected'] == selection['selected'] == 607
    assert generation['selection_audit_sha256'] == sha(folder / 'selection_audit.json')
    assert generation['build_log_sha256'] == sha(folder / 'build.log')
    for path, digest in selection['inputs'].items():
        assert sha(folder / path) == digest, path
    planned = {name.replace('\\', '/') for name in
               (folder / 'selected-elfs.txt').read_text(encoding='utf-8').splitlines()}
    assert len(planned) == 607
    suites = Counter(name.split('/')[1] for name in planned)
    declared = dict((name, int(count)) for name, count in re.findall(
        r'^\|\s*([A-Za-z0-9_]+)\s*\|\s*(\d+)\s*\|$',
        (work / 'test_list.md').read_text(encoding='utf-8'), re.MULTILINE))
    assert suites == declared == dict(selection['suites'])
    build_log = (folder / 'build.log').read_text(encoding='utf-8')
    assert 'Certification mode: selected certificate RVA23.' in build_log
    assert 'Build complete: 2428 succeeded' in build_log
    assert 'LOCAL COMPATIBILITY MODE' not in build_log
    elfs = {path.relative_to(work / 'elfs').as_posix(): sha(path)
            for path in (work / 'elfs').rglob('*.elf')}
    assert set(elfs) == planned and elfs == generation['elf_sha256']
    model_path = ROOT / 'out/act4/dut/model.json'
    model = read(model_path)
    assert model['passed'] and sha(ROOT / model['binary']) == model['binary_sha256']
    for path, digest in model['inputs'].items():
        assert sha(ROOT / path) == digest, path
    reference_path = ROOT / 'out/act4/sail-0.16/driver_report.json'
    reference = read(reference_path)
    assert reference['passed'] and reference['model_commit'] == SAIL_REVISION
    assert reference['model_version'] == '0.16'
    assert sha(ROOT / reference['binary']) == reference['binary_sha256']
    report_path = ROOT / 'out/act4/dut/current-rva23-checked-in.json'
    report = read(report_path)
    assert report['act_commit'] == REVISION and report['model_sha256'] == sha(model_path)
    assert report['binary_sha256'] == model['binary_sha256']
    assert report['passed'] == report['executed'] == 607 and report['failed'] == 0
    assert set(report['results']) == set(report['selected']) == planned
    sources, signatures, logs = {}, {}, {}
    for name in sorted(planned):
        result = report['results'][name]
        assert result['passed'] and result['exit_code'] == 0 and not result['timed_out'], name
        assert result['elf_sha256'] == elfs[name] and result['witnesses'], name
        log_path = ROOT / result['log']
        assert sha(log_path) == result['log_sha256'], name
        log = log_path.read_text(encoding='utf-8', errors='replace')
        assert 'PASS rv_act4_program_tb' in log and 'RVCP-SUMMARY: TEST FAILED' not in log
        assert all(witness in log for witness in result['witnesses']), name
        logs[name] = result['log_sha256']
        stem = name.removesuffix('.elf')
        source = ROOT / SOURCE / 'tests' / (stem + '.S')
        sources[stem] = sha(source)
        signatures[stem] = sha(work / 'build' / (stem + '.sig'))
        sail_log = work / 'build' / (stem + '.sig.log')
        assert 'PASS Sail HTIF' in sail_log.read_text(encoding='utf-8', errors='replace'), name
        logs[stem + '.sail'] = sha(sail_log)
    dump(folder / 'execution_audit.json', dict(
        passed=True, full_profile_verified=False,
        scope='607 checked-in ELFs selected by upstream RVA23 filter; generated vector inventory and normative coverage remain separate',
        act_commit=REVISION, required_sail='0.16', sail_commit=SAIL_REVISION,
        selected=607, executed=607, failed=0, suites=declared,
        report_sha256=sha(report_path), model_sha256=sha(model_path),
        reference_report_sha256=sha(reference_path), reference_binary_sha256=reference['binary_sha256'],
        selection_audit_sha256=sha(folder / 'selection_audit.json'),
        generation_audit_sha256=sha(folder / 'generation_audit.json'),
        framework_config_sha256=sha(framework), source_sha256=sources,
        elf_sha256=elfs, signatures_sha256=signatures, log_sha256=logs,
        audit_sha256=sha(__file__)))
    print('PASS upstream RVA23 checked-in selection: 607 Sail/RTL ELFs, 34 suites', flush=True)


if __name__ == '__main__':
    main()

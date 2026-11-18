"""Audit the generated upstream vector selection and its Sail/RTL execution."""

import argparse
import json
import re
from collections import Counter
from pathlib import PurePosixPath

from prepare_act4_current_vector import FOLDER, GENERATION_LOG, NAME, SUITES
from run_act4_current_h import REVISION, SAIL_REVISION, SOURCE, git
from sim_runner import ROOT, dump, sha


def read(path):
    return json.loads(path.read_bytes())


def audit_selection(folder, work):
    manifest_path = folder / 'source_manifest.json'
    manifest = read(manifest_path)
    assert manifest['prepared'] and manifest['act_commit'] == REVISION
    assert manifest['source_count'] == 2301 and set(manifest['suites']) == set(SUITES)
    assert manifest['prepare_script_sha256'] == sha(ROOT / 'scripts/prepare_act4_current_vector.py')
    assert manifest['generation_log_sha256'] == sha(ROOT / GENERATION_LOG)
    assert 'Generated 30 test suite(s)' in (ROOT / GENERATION_LOG).read_text(encoding='utf-8')
    actual_sources = {path.relative_to(folder).as_posix(): sha(path)
                      for path in (folder / 'tests/rv64i').rglob('*.S')}
    assert actual_sources == manifest['source_sha256'] and len(actual_sources) == 2301
    for path, digest in manifest['generator_sha256'].items():
        assert sha(ROOT / SOURCE / path) == digest, path
    for prefix, entries in (('config/', manifest['config_sha256']), ('', manifest['env_sha256'])):
        for path, digest in entries.items():
            assert sha(folder / (prefix + path)) == digest, path
    selection = work / 'test_list.md'
    counts = dict((suite, int(count)) for suite, count in re.findall(
        r'^\|\s*([A-Za-z0-9_]+)\s*\|\s*(\d+)\s*\|$',
        selection.read_text(encoding='utf-8'), re.MULTILINE))
    assert counts == manifest['suites']
    planned = {path.removeprefix('tests/').removesuffix('.S') + '.elf' for path in actual_sources}
    assert Counter(path.split('/')[1] for path in planned) == counts
    result = dict(selection_verified=True, act_commit=REVISION, selected=len(planned),
                  suites=counts, source_manifest_sha256=sha(manifest_path),
                  selection_sha256=sha(selection), audit_sha256=sha(__file__))
    dump(folder / 'selection_audit.json', result)
    return planned, result


def audit_generation(folder, work, planned):
    framework_log = folder / 'framework.log'
    log = framework_log.read_text(encoding='utf-8')
    summary = re.search(r'Build complete: ([^\r\n]+)', log)
    assert summary and 'failed' not in summary[1]
    assert sum(map(int, re.findall(r'(\d+) (?:succeeded|up-to-date)', summary[1]))) == 4 * len(planned)
    assert 'LOCAL COMPATIBILITY MODE' not in log
    assert 'Certification mode: selected certificate RVA23.' in log
    framework = ROOT / SOURCE / 'framework/src/act/config.py'
    assert 'REQUIRED_SAIL_VERSION = "0.16"' in framework.read_text(encoding='utf-8')
    reference_path = ROOT / 'out/act4/sail-0.16/driver_report.json'
    reference = read(reference_path)
    assert reference['passed'] and reference['model_version'] == '0.16'
    assert reference['model_commit'] == SAIL_REVISION
    assert sha(ROOT / reference['binary']) == reference['binary_sha256']
    elfs = {path.relative_to(work / 'elfs').as_posix(): sha(path)
            for path in (work / 'elfs').rglob('*.elf')}
    assert set(elfs) == planned
    signatures, logs = {}, {}
    for name in sorted(planned):
        stem = name.removesuffix('.elf')
        source_name = PurePosixPath(name).with_suffix('.S').name
        signatures[stem] = sha(work / 'build' / (stem + '.sig'))
        sail_log = work / 'build' / (stem + '.sig.log')
        sail_output = sail_log.read_text(encoding='utf-8', errors='replace')
        assert 'PASS Sail HTIF' in sail_output, name
        assert f'TEST SIGRUN - Test File "{source_name}"' in sail_output, name
        logs[stem] = sha(sail_log)
    result = dict(build_passed=True, act_commit=REVISION, required_sail='0.16',
                  sail_commit=SAIL_REVISION, generated=len(planned),
                  framework_config_sha256=sha(framework), framework_log_sha256=sha(framework_log),
                  reference_report_sha256=sha(reference_path),
                  reference_binary_sha256=reference['binary_sha256'],
                  elf_sha256=elfs, signatures_sha256=signatures, sail_log_sha256=logs)
    dump(folder / 'generation_audit.json', result)
    return result


def audit_execution(folder, planned, selection, generation):
    model_path = ROOT / 'out/act4/dut/model.json'
    model = read(model_path)
    assert model['passed'] and sha(ROOT / model['binary']) == model['binary_sha256']
    for path, digest in model['inputs'].items():
        assert sha(ROOT / path) == digest, path
    report_path = ROOT / 'out/act4/dut/current-rva23-vector.json'
    report = read(report_path)
    assert report['act_commit'] == REVISION and report['model_sha256'] == sha(model_path)
    assert report['binary_sha256'] == model['binary_sha256']
    assert report['passed'] == report['executed'] == len(planned) and report['failed'] == 0
    assert set(report['results']) == set(report['selected']) == planned
    elfs = generation['elf_sha256']
    logs = {}
    for name in sorted(planned):
        result = report['results'][name]
        assert result['passed'] and result['exit_code'] == 0 and not result['timed_out'], name
        assert result['elf_sha256'] == elfs[name] and result['witnesses'], name
        run_log = ROOT / result['log']
        assert sha(run_log) == result['log_sha256'], name
        output = run_log.read_text(encoding='utf-8', errors='replace')
        assert 'PASS rv_act4_program_tb' in output and 'RVCP-SUMMARY: TEST FAILED' not in output
        assert all(witness in output for witness in result['witnesses']), name
        source_name = PurePosixPath(name).with_suffix('.S').name
        expected_pass = f'RVCP-SUMMARY: TEST PASSED - Test File "{source_name}"'
        assert expected_pass in result['witnesses'], name
        logs[name] = result['log_sha256']
    dump(folder / 'execution_audit.json', dict(
        passed=True, full_profile_verified=False, act_commit=REVISION,
        required_sail='0.16', sail_commit=SAIL_REVISION,
        selected=len(planned), executed=len(planned), failed=0,
        selection=selection, selection_audit_sha256=sha(folder / 'selection_audit.json'),
        report_sha256=sha(report_path), model_sha256=sha(model_path),
        generation_audit_sha256=sha(folder / 'generation_audit.json'),
        elf_sha256=elfs, log_sha256=logs, audit_sha256=sha(__file__)))
    print(f'PASS current upstream vector execution: {len(planned)} Sail/RTL ELFs', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--selection-only', action='store_true',
                        help='Verify generated source and selection evidence before execution completes')
    modes.add_argument('--generation-only', action='store_true',
                       help='Verify Sail signatures and final ELFs before RTL execution completes')
    args = parser.parse_args()
    assert git('rev-parse', 'HEAD') == REVISION
    git('diff', '--exit-code', 'HEAD', '--', 'framework', 'generators', 'testplans', 'tests')
    folder = ROOT / FOLDER
    work = folder / 'work' / NAME
    planned, selection = audit_selection(folder, work)
    if args.selection_only:
        print(f'PASS current vector source selection: {len(planned)} sources, {len(SUITES)} suites', flush=True)
    else:
        generation = audit_generation(folder, work, planned)
        if args.generation_only:
            print(f'PASS current vector generation: {len(planned)} Sail signatures and final ELFs', flush=True)
        else:
            audit_execution(folder, planned, selection, generation)


if __name__ == '__main__':
    main()

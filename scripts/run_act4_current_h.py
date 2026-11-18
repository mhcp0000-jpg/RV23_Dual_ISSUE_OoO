"""Run H and PMP suites with upstream ACT4's Sail 0.16 requirement."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

from run_act4_upstream_h import EXCLUDED, SOURCE_H, SOURCE_PMP, NAME as OLD_NAME, dut_configs
from sim_runner import ROOT, dump, sha


REVISION = '8adba12816e0e99c46ccf01626752dbf2e1e40fb'
SAIL_REVISION = 'e5acebb04ff573e93203596486b831a5974117c3'
SOURCE = 'out/act4/upstream_act4_current'
RUN = 'out/act4/current_h_probe'
NAME = 'rv23-RVA23S64-current-h-probe'
REPORT = 'current-h-probe.json'
TESTS = (
    'priv/Sv/Sv_H_sv39x4_atp_mode-00',
    'priv/Sv/Sv_H_sv39x4_g_pte-00',
    'priv/Sv/Sv_HSm_sv39x4_guest_faults_vs-00',
    'priv/Svinval/Svinval_H_Svinval_hstatus_vtvm-00',
)


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT / SOURCE), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def build(files, configs, workers, run, name, report):
    for filename in files:
        destination = ROOT / run / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / SOURCE / filename, destination)
    config_dir = ROOT / run / 'config'
    config_dir.mkdir(parents=True, exist_ok=True)
    for filename, contents in configs.items():
        (config_dir / filename).write_text(contents, encoding='utf-8')
    prefix = 'C:/rv_workspaces/rv23/'
    env = {**os.environ, 'RV23_ACT4_PYTHON': '3.13',
           'RV23_ACT4_SOURCE_ROOT': prefix + SOURCE,
           'RV23_ACT4_CONFIG': prefix + run + '/config/test_config.yaml',
           'RV23_ACT4_WORKDIR': prefix + run + '/work',
           'RV23_ACT4_LOG': run.removeprefix('out/act4/') + '/framework.log'}
    subprocess.run([sys.executable, 'scripts/run_act4.py', '--test-dir', prefix + run + '/tests',
                    '--jobs', str(workers), '--keep-going'], cwd=ROOT, env=env, check=True)
    subprocess.run([sys.executable, 'scripts/run_act4_dut.py', '--act-source-root', SOURCE,
                    '--elf-root', f'{run}/work/{name}/elfs', '--report', report,
                    '--workers', str(workers), '--timeout', '1200'], cwd=ROOT, check=True)


def audit(files, configs, run, name, report_name, tests, excluded):
    folder = ROOT / run
    work = folder / 'work' / name
    framework_log = folder / 'framework.log'
    log = framework_log.read_text(encoding='utf-8')
    summary = re.search(r'Build complete: ([^\r\n]+)', log)
    assert summary and 'failed' not in summary[1] and 'LOCAL COMPATIBILITY MODE' not in log
    assert sum(map(int, re.findall(r'(\d+) (?:succeeded|up-to-date)', summary[1]))) == 4 * len(tests)
    source_hashes = {filename: sha(ROOT / SOURCE / filename) for filename in files}
    assert all(sha(folder / filename) == digest for filename, digest in source_hashes.items())
    assert all((folder / 'config' / filename).read_text(encoding='utf-8') == contents
               for filename, contents in configs.items())
    reference_dir = ROOT / 'out/act4/sail-0.16'
    reference = json.loads((reference_dir / 'driver_report.json').read_bytes())
    assert reference['passed'] and reference['model_version'] == '0.16', reference
    assert reference['model_commit'] == SAIL_REVISION
    assert sha(reference_dir / 'sail_act4_reference.exe') == reference['binary_sha256']
    model_path = ROOT / 'out/act4/dut/model.json'
    model = json.loads(model_path.read_bytes())
    assert model['passed'] and sha(ROOT / model['binary']) == model['binary_sha256']
    assert all(sha(ROOT / path) == digest for path, digest in model['inputs'].items())
    report_path = ROOT / 'out/act4/dut' / report_name
    report = json.loads(report_path.read_bytes())
    assert report['act_commit'] == REVISION and report['model_sha256'] == sha(model_path)
    assert report['binary_sha256'] == model['binary_sha256']
    assert report['passed'] == report['executed'] == len(tests) and report['failed'] == 0
    elfs = {path.relative_to(work / 'elfs').as_posix(): sha(path)
            for path in (work / 'elfs').rglob('*.elf')}
    assert set(elfs) == set(report['results']) == {name + '.elf' for name in tests}
    for filename, result in report['results'].items():
        assert result['passed'] and result['exit_code'] == 0 and not result['timed_out'], filename
        assert result['elf_sha256'] == elfs[filename] and result['witnesses'], filename
        run_log = ROOT / result['log']
        assert sha(run_log) == result['log_sha256']
        output = run_log.read_text(encoding='utf-8', errors='replace')
        assert all(witness in output for witness in result['witnesses'])
        assert 'PASS rv_act4_program_tb' in output and 'RVCP-SUMMARY: TEST FAILED' not in output
    dump(folder / 'audit.json', dict(passed=True, act_commit=REVISION, required_sail='0.16',
         sail_commit=SAIL_REVISION,
         reference_binary_sha256=reference['binary_sha256'], source_sha256=source_hashes,
         framework_config_sha256=sha(ROOT / SOURCE / 'framework/src/act/config.py'),
         build_log_sha256=sha(framework_log), report_sha256=sha(report_path),
         config_sha256={name: sha(folder / 'config' / name) for name in configs},
         signatures_sha256={name: sha(work / 'build' / (name + '.sig')) for name in tests},
         excluded_sources=sorted(excluded),
         elf_sha256=elfs, audit_sha256=sha(__file__)))
    print(f'PASS current upstream ACT4, required Sail 0.16 and {len(elfs)} H/PMP RTL ELFs', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Recheck local run evidence')
    parser.add_argument('--extended', action='store_true',
                        help='Run the H, Sv39x4 and PMP selection from the supplemental suite')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if not args.check and not (ROOT / SOURCE / '.git').exists():
        subprocess.run(['git', 'init', str(ROOT / SOURCE)], check=True)
        git('fetch', '--depth', '1', 'https://github.com/riscv/riscv-arch-test.git', REVISION)
        git('checkout', '--detach', REVISION)
    assert git('rev-parse', 'HEAD') == REVISION
    git('diff', '--exit-code', 'HEAD', '--', 'framework', 'tests', 'uv.lock', 'pyproject.toml')
    framework = (ROOT / SOURCE / 'framework/src/act/config.py').read_text(encoding='utf-8')
    assert 'REQUIRED_SAIL_VERSION = "0.16"' in framework
    run, name, report = RUN, NAME, REPORT
    selected = [f'tests/{test}.S' for test in TESTS]
    excluded = set()
    if args.extended:
        run, name, report = ('out/act4/current_h_extended', 'rv23-RVA23S64-current-h-extended',
                             'current-h-extended.json')
        candidates = git('ls-tree', '-r', '--name-only', 'HEAD', 'tests/priv').splitlines()
        selected = [path for path in candidates
                    if re.match(r'^tests/priv/(Sv|Svinval|Svnapot|Svpbmt|PMP)/.*\.S$', path)
                    and (SOURCE_H.search(path) or SOURCE_PMP.search(path))]
        assert len(selected) == 42 and EXCLUDED <= set(selected)
        excluded = EXCLUDED
    tests = [path.removeprefix('tests/').removesuffix('.S') for path in selected if path not in excluded]
    files = selected + git('ls-tree', '-r', '--name-only', 'HEAD', 'tests/env').splitlines()
    configs = {filename: contents.replace(OLD_NAME, name) for filename, contents in dut_configs().items()}
    if not args.check:
        build(files, configs, args.workers, run, name, report)
    audit(files, configs, run, name, report, tests, excluded)


if __name__ == '__main__':
    main()

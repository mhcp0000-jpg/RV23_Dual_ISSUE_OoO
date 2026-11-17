"""Build and audit the supplemental upstream ACT4 H, Sv39x4 and PMP tests."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

from sim_runner import ROOT, dump, sha


ACT = ROOT / 'out/act4'
UPSTREAM = ACT / 'upstream_act4_review'
RUN = ACT / 'upstream_h_extended'
REVISION = '1c3e9f2a89e103eeed0a3e6ba1bc699f100fd481'
NAME = 'rv23-RVA23S64-h-extended'
REPORT = 'upstream-h-extended.json'
SOURCE_PMP = re.compile(r'PMP_Sm_cfg_L_modify_(napot|off|tor)-00\.S$')
SOURCE_H = re.compile(r'_(H|HSm|HSvZicbo|HZicbo)_.*(sv39x4|hstatus)')
EXCLUDED = {
    'tests/priv/Sv/Sv_HSm_sv39x4_ldst_straddle-00.S',
    'tests/priv/Sv/Sv_H_sv39x4_ldst_straddle-00.S',
}
HPM_HEADER = '''#ifndef UDB_HPM_COUNTER3_WIDTH
#define UDB_HPM_COUNTER3_WIDTH 64
#endif
#define RVMODEL_HPM_COUNTER 3
#define RVMODEL_MHPMEVENT_VAL 2
#define RVMODEL_MHPMEVENT_CODE(_R1, _R2) fence

'''


def git(*args):
    return subprocess.check_output(['git', '-C', str(UPSTREAM), *args], text=True).strip()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def selected_sources():
    assert git('rev-parse', 'HEAD') == REVISION
    assert not git('diff', '--name-only', 'HEAD', '--', 'tests', 'framework')
    tracked = git('ls-tree', '-r', '--name-only', 'HEAD', 'tests').splitlines()
    cases = [p for p in tracked if re.match(r'^tests/priv/(Sv|Svinval|Svnapot|Svpbmt|PMP)/.*\.S$', p)
             and (SOURCE_H.search(p) or SOURCE_PMP.search(p))]
    assert len(cases) == 42
    return cases, [p for p in tracked if p.startswith('tests/env/')]


def dut_configs():
    base = ROOT / 'config/act4/rv23'
    names = ('rv23.yaml', 'test_config.yaml', 'link.ld', 'rvmodel_macros.h', 'sail.json')
    files = {name: (base / name).read_text(encoding='utf-8') for name in names}
    for name in ('rv23.yaml', 'test_config.yaml'):
        assert files[name].count('name: rv23-RVA23S64') == 1
        files[name] = files[name].replace('name: rv23-RVA23S64', f'name: {NAME}')
    header = files['rvmodel_macros.h']
    end = header.rindex('#endif')
    files['rvmodel_macros.h'] = header[:end] + HPM_HEADER + header[end:]
    return files


def build(args, cases, test_env, configs):
    for name in cases + test_env:
        source, destination = UPSTREAM / name, RUN / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_file() or sha(source) != sha(destination):
            shutil.copy2(source, destination)
    config = RUN / 'config'
    config.mkdir(exist_ok=True)
    for name, contents in configs.items():
        path = config / name
        if not path.is_file() or path.read_text(encoding='utf-8') != contents:
            path.write_text(contents, encoding='utf-8')

    # The Windows toolchain uses the project's established ASCII junction.
    prefix = 'C:/rv_workspaces/rv23/'
    env = {**os.environ, 'RV23_ACT4_PYTHON': '3.13',
           'RV23_ACT4_SOURCE_ROOT': prefix + relative(UPSTREAM),
           'RV23_ACT4_CONFIG': prefix + relative(config / 'test_config.yaml'),
           'RV23_ACT4_WORKDIR': prefix + relative(RUN / 'work'),
           'RV23_ACT4_LOG': relative(RUN / 'framework_recheck.log').removeprefix('out/act4/')}
    subprocess.run([sys.executable, 'scripts/run_act4.py', '--test-dir', prefix + relative(RUN / 'tests'),
                    '--jobs', str(args.workers), '--keep-going'], cwd=ROOT, env=env, check=True)
    subprocess.run([sys.executable, 'scripts/run_act4_dut.py', '--act-source-root', relative(UPSTREAM),
                    '--elf-root', relative(RUN / 'work' / NAME / 'elfs'), '--report', REPORT,
                    '--workers', str(args.workers), '--timeout', '1200'], cwd=ROOT, check=True)


def audit(cases, test_env, configs):
    assert {relative(path).removeprefix(relative(RUN) + '/')
            for path in (RUN / 'tests/priv').rglob('*.S')} == set(cases)
    source_hashes = {path: sha(RUN / path) for path in cases + test_env}
    assert all(sha(UPSTREAM / name) == digest for name, digest in source_hashes.items())
    config_dir = RUN / 'config'
    assert all((config_dir / name).read_text(encoding='utf-8') == contents for name, contents in configs.items())
    root = RUN / 'work' / NAME / 'elfs'
    elfs = {path.relative_to(root).as_posix(): sha(path) for path in root.rglob('*.elf')}
    assert {'tests/' + name.removesuffix('.elf') + '.S' for name in elfs} == set(cases) - EXCLUDED
    report_path = ACT / 'dut' / REPORT
    report = json.loads(report_path.read_bytes())
    model_path = ACT / 'dut/model.json'
    model = json.loads(model_path.read_bytes())
    assert model['passed']
    assert all(sha(ROOT / path) == digest for path, digest in model['inputs'].items())
    assert model['binary_sha256'] == report['binary_sha256'] == sha(ROOT / model['binary'])
    assert report['act_commit'] == REVISION and report['model_sha256'] == sha(model_path)
    assert set(report['results']) == set(report['selected']) == set(elfs)
    assert report['passed'] == report['executed'] == len(elfs) == 40 and report['failed'] == 0
    for name, result in report['results'].items():
        assert result['passed'] and result['exit_code'] == 0 and not result['timed_out'], name
        assert result['elf_sha256'] == elfs[name] and result['witnesses'], name
        log = ROOT / result['log']
        assert sha(log) == result['log_sha256'], log
        text = log.read_text(encoding='utf-8', errors='replace')
        assert all(witness in text for witness in result['witnesses']), log
        assert 'PASS rv_act4_program_tb' in text and 'RVCP-SUMMARY: TEST FAILED' not in text, log
    dump(RUN / 'audit.json', dict(passed=True, act_commit=REVISION, source_sha256=source_hashes,
        elf_sha256=elfs, excluded_sources=sorted(EXCLUDED), report_sha256=sha(report_path),
        config_sha256={name: sha(config_dir / name) for name in configs},
        reference_sha256=sha(ACT / 'sail-0.16/sail_act4_reference.exe'),
        build_log_sha256=sha(RUN / 'framework_recheck.log'), audit_sha256=sha(__file__)))
    print('PASS supplemental ACT4 H and PMP evidence: 40 current RTL ELFs', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Audit existing build and execution artifacts')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if not args.check and not UPSTREAM.exists():
        subprocess.run(['git', 'init', str(UPSTREAM)], check=True)
        subprocess.run(['git', '-C', str(UPSTREAM), 'fetch', '--depth', '1',
                        'https://github.com/riscv/riscv-arch-test.git', REVISION], check=True)
        subprocess.run(['git', '-C', str(UPSTREAM), 'checkout', '--detach', REVISION], check=True)
    inputs = (*selected_sources(), dut_configs())
    if not args.check:
        build(args, *inputs)
    audit(*inputs)


if __name__ == '__main__':
    main()

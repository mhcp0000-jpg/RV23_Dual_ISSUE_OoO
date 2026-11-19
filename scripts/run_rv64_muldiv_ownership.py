"""Content-bound XLEN64 M-unit flush/backpressure/tag ownership checks."""
import argparse
import json
import re

from sim_runner import ROOT, Simulator, dump, sha, source_inputs

FOLDER = ROOT / 'out/rva23/rv64_muldiv_ownership'
TOP = 'rv64_muldiv_ownership_tb'


def verify(log):
    match = re.search(r'MULDIV_OWNERSHIP cases=(\d+) killed=(\d+) preserved=(\d+) reused=(\d+) results=(\d+) zero_dest=(\d+)', log)
    assert match and tuple(map(int, match.groups())) == (20, 12, 8, 12, 24, 4)
    assert 'PASS ' + TOP in log
    return dict(zip(('cases', 'killed', 'preserved', 'reused', 'results', 'zero_dest'), map(int, match.groups())))


def check(report, files):
    assert report['passed'] and report['driver_sha256'] == sha(__file__)
    model = report['model']
    assert model['inputs'] == source_inputs(files) and model['top'] == TOP
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    for step in ('compile', 'build'):
        run = model[step]
        assert run['passed'] and run['exit_code'] == 0 and sha(ROOT / run['log']) == run['log_sha256']
    run = report['run']
    assert run['passed'] and run['exit_code'] == 0 and sha(ROOT / run['log']) == run['log_sha256']
    log = (ROOT / run['log']).read_text(encoding='utf-8')
    assert report['outcomes'] == verify(log)
    controls = []
    for original in ('killed=12', 'preserved=8', 'reused=12', 'results=24'):
        broken = log.replace(original, original.split('=')[0] + '=0')
        assert broken != log
        try:
            verify(broken)
        except AssertionError:
            controls.append(original)
        else:
            raise AssertionError('Missing ownership witness accepted')
    return report['outcomes'], controls


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + ['tb/' + TOP + '.sv']
    FOLDER.mkdir(parents=True, exist_ok=True)
    if args.check:
        report = json.loads((FOLDER / 'report.json').read_bytes())
    else:
        with Simulator() as sim:
            model = sim.build('rv64_muldiv_ownership', TOP, files)
            run = sim.simulate(model)
        log = (ROOT / run['log']).read_text(encoding='utf-8')
        report = dict(passed=True, complete_profile_validation=False, driver_sha256=sha(__file__),
            model=model, run=run, outcomes=verify(log), scope='XLEN64 component flush/tag/backpressure scenarios, full and word data paths; not all operations, production branch/interrupt schedules or full core retirement proof')
        dump(FOLDER / 'report.json', report)
    print('PASS XLEN64 M ownership', *check(report, files), flush=True)


if __name__ == '__main__':
    main()

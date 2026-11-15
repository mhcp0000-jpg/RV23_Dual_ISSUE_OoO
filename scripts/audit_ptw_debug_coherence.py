"""Audit production PTW/debug coherence evidence and its stale-cache control."""
import argparse
import json
import re

from sim_runner import ROOT, dump, sha, source_inputs


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-negative', action='store_true')
    args = parser.parse_args()
    folder = ROOT / 'out/rva23/ptw_debug_coherence'
    report = read(folder / 'report.json')
    assert report['passed'] and report['generator_sha256'] == sha(ROOT / 'scripts/run_ptw_debug_coherence.py')
    model = report['model']
    required = source_inputs((ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines())
    assert all(model['inputs'].get(path) == digest for path, digest in required.items())
    for path, digest in model['inputs'].items():
        assert sha(ROOT / path) == digest, path
    for path, digest in report['runtime_inputs'].items():
        assert sha(ROOT / path) == digest, path
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    assert sha(ROOT / 'sw/tests/rv64_ptw_debug_coherence.S') == report['source_sha256']
    assert sha(folder / 'test.elf') == report['elf_sha256']
    assert sha(folder / 'commit.csv') == report['trace_sha256']
    for phase in ['compile', 'run']:
        run = report[phase]
        assert run['passed'] and run['exit_code'] == 0
        assert sha(ROOT / run['log']) == run['log_sha256']
    log = (ROOT / report['run']['log']).read_text(encoding='utf-8')
    phases = re.findall(r'\[host-event kind=0 data=0x505400([0-9a-f]{2})\]', log)
    assert phases == [f'{n:02x}' for n in range(1, 17)]
    match = re.search(r'PTW DEBUG COHERENCE PASS updates=(\d+) pte_responses=(\d+) pte_hits=(\d+) resident_snoops=(\d+)', log)
    assert match and 'PASS rv32_program_tb' in log
    assert 'PTW DEBUG MODES halted=8 running=8' in log
    updates, responses, hits, snoops = map(int, match.groups())
    assert updates == 16 and responses >= 17 and hits >= 16 and snoops >= 16
    negative_sha = None
    if args.with_negative:
        negative_path = ROOT / 'out/negative_controls/ptw_debug_coherence/report.json'
        negative = read(negative_path)
        assert negative['passed'] and negative['positive_report_sha256'] == sha(folder / 'report.json')
        assert negative['generator_sha256'] == sha(ROOT / 'scripts/check_ptw_debug_coherence_negative.py')
        assert negative['elf_sha256'] == report['elf_sha256']
        assert negative['original_sha256'] == sha(ROOT / 'rtl/soc/rv23_cache.sv')
        mutant = 'out/negative_controls/ptw_debug_coherence/rv23_cache.sv'
        assert sha(ROOT / mutant) == negative['mutant_sha256']
        expected = dict(model['inputs'])
        del expected['rtl/soc/rv23_cache.sv']
        expected[mutant] = negative['mutant_sha256']
        assert negative['model']['inputs'] == expected
        assert sha(ROOT / negative['model']['binary']) == negative['model']['binary_sha256']
        run = negative['run']
        assert run['passed'] and run['exit_code'] != 0
        assert run['expected_failure'] == 'Stale PTE response after update 1:'
        assert sha(ROOT / run['log']) == run['log_sha256']
        assert run['expected_failure'] in (ROOT / run['log']).read_text(encoding='utf-8')
        negative_sha = sha(negative_path)
    dump(folder / 'audit.json', dict(passed=True, complete_profile_validation=False,
        scope='Finite coherent resident-PTE reads after ordered external debug updates and native resume/SFENCE.VMA',
        audit_sha256=sha(__file__), report_sha256=sha(folder / 'report.json'),
        updates=updates, pte_responses=responses, pte_hits=hits, resident_snoops=snoops,
        negative_control_required=args.with_negative, negative_report_sha256=negative_sha))
    print('PASS current PTW/debug evidence:', updates, 'updates,', hits, 'PTE hits; negative control:', args.with_negative)


if __name__ == '__main__':
    main()

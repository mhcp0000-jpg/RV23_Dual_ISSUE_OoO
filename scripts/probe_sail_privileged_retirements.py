"""Inspect exact privileged Sail/RTL prefixes without masking any CSR values.

This probe reports differences, including expected cycle/counter/platform
differences, for subsequent analysis. It never changes the passing user audit.
"""
import csv
import json

from sim_runner import ROOT, dump, sha


def normalize(row):
    instruction = int(row['instruction'], 16)
    if instruction & 3 != 3:
        instruction &= 0xffff
    trap = row['trap'] == '1'
    write = row['rd_write'] == '1' and (row['rd_fp'] == '1' or int(row['rd']) != 0)
    return dict(pc=int(row['pc'], 16), instruction=instruction, trap=trap,
                cause=int(row['cause']) if trap else 0,
                writeback=(int(row['rd_fp']), int(row['rd']), int(row['wdata'], 16)) if write else None)


def main():
    path = ROOT / 'out/rva23/sail_upstream_comparison/report.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    assert report['passed'] and not report['reference_only']
    for name, digest in {**report['inputs'], **report['model']['inputs']}.items():
        assert sha(ROOT / name) == digest, name
    assert sha(ROOT / report['model']['binary']) == report['model']['binary_sha256']
    assert sha(ROOT / report['reference']['binary']) == report['reference']['binary_sha256']
    callback_sha = sha(ROOT / 'scripts/reference/sail_trace_callbacks.h')
    assert callback_sha == report['reference']['trace_driver_sha256']
    cases = [c for c in report['cases'] if c['name'].startswith(('rv64mi/', 'rv64si/'))]
    assert len(cases) == 16
    results = []
    for case in cases:
        assert case['reference_passed'] and case['rtl_passed']
        for key in ['elf', 'sail_trace', 'rtl_trace']:
            assert sha(ROOT / case[key]) == case[key + '_sha256']
        with (ROOT / case['sail_trace']).open(newline='') as f:
            reference = list(csv.DictReader(f))
        with (ROOT / case['rtl_trace']).open(newline='') as f:
            actual = list(csv.DictReader(f))
        start = next(i for i, row in enumerate(actual) if int(row['pc'], 16) == int(reference[0]['pc'], 16))
        mismatch, compared = None, 0
        for expected, candidate in zip(reference, actual[start:]):
            if normalize(expected) != normalize(candidate):
                mismatch = dict(index=compared, sail=expected, rtl=candidate)
                break
            compared += 1
        if mismatch is None and compared != len(reference):
            mismatch = dict(index=compared, error='RTL prefix shorter than Sail')
        results.append(dict(name=case['name'], matched=mismatch is None, compared=compared,
                            first_mismatch=mismatch, elf_sha256=case['elf_sha256'],
                            sail_trace_sha256=case['sail_trace_sha256'], rtl_trace_sha256=case['rtl_trace_sha256']))
        print('MATCH' if mismatch is None else 'DIFF', case['name'], 'prefix', compared,
              '' if mismatch is None else json.dumps({k:mismatch.get(k) for k in ['sail', 'rtl']}, ensure_ascii=False), flush=True)
    dump(ROOT / 'out/rva23/sail_privileged_retirement_probe.json', dict(
        scope='Unmasked first-divergence analysis of 16 privileged traces; differences are not classified as RTL defects',
        generator_sha256=sha(__file__), input_report_sha256=sha(path), cases=results,
        reference_trace_callback_sha256=callback_sha,
        exact_matches=sum(c['matched'] for c in results),
        exact_matched_retirements=sum(c['compared'] for c in results if c['matched'])))


if __name__ == '__main__':
    main()

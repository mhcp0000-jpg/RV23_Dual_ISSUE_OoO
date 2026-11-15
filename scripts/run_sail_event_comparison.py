"""Compare privileged reference/RTL events including interrupt entry and WFI.

Uses saved identical ELFs and RTL traces, and the same official Sail libraries
with a separate observation callback. No arithmetic/CSR value is masked.
"""
import csv
import json
import os

from sim_runner import ROOT, Simulator, dump, sha


def normalize(row):
    instruction = int(row['instruction'], 16)
    if instruction & 3 != 3:
        instruction &= 0xffff
    trap = row['trap'] == '1'
    write = row['rd_write'] == '1' and (row['rd_fp'] == '1' or int(row['rd']) != 0)
    return dict(pc=int(row['pc'], 16), instruction=instruction, trap=trap,
                cause=int(row['cause']) if trap else 0,
                writeback=(int(row['rd_fp']), int(row['rd']), int(row['wdata'], 16)) if write else None)


def compare(reference, actual):
    start = next(i for i, row in enumerate(actual) if int(row['pc'], 16) == int(reference[0]['pc'], 16))
    for index, expected in enumerate(reference):
        candidate = actual[start + index] if start + index < len(actual) else None
        if candidate is None or normalize(expected) != normalize(candidate):
            return index, dict(index=index, sail=expected, rtl=candidate)
    return len(reference), None


def read_csv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    base_path = ROOT / 'out/rva23/sail_upstream_comparison/report.json'
    driver_path = ROOT / 'out/reference/sail-event-driver/report.json'
    base = json.loads(base_path.read_text(encoding='utf-8'))
    driver = json.loads(driver_path.read_text(encoding='utf-8'))
    assert base['passed'] and driver['passed']
    for name, digest in {**base['inputs'], **base['model']['inputs'], **driver['inputs']}.items():
        assert sha(ROOT / name) == digest, name
    assert sha(ROOT / driver['binary']) == driver['binary_sha256']
    assert sha(ROOT / base['model']['binary']) == base['model']['binary_sha256']
    assert driver['base_report_sha256'] == sha(ROOT / 'out/reference/sail-riscv-0.16-cygwin/build_report.json')
    cases = [c for c in base['cases'] if c['name'].startswith(('rv64mi/', 'rv64si/'))]
    assert len(cases) == 16
    config = ROOT / 'config/reference/sail-rv23.json'
    folder = ROOT / 'out/rva23/sail_privileged_events'
    folder.mkdir(parents=True, exist_ok=True)
    result = dict(passed=False, complete_profile_validation=False,
        scope='Exact M/S test prefixes including WFI and interrupt events; PC/raw instruction/trap/cause/scalar writeback, no cycle or full privileged-state equivalence claim',
        generator_sha256=sha(__file__), base_report_sha256=sha(base_path),
        driver_report_sha256=sha(driver_path), config_sha256=sha(config), cases=[])
    dump(folder / 'report.json', result)
    with Simulator() as sim:
        sim.env['PATH'] = 'C:/rv_toolchains/cygwin-rv23/bin;' + os.environ['PATH']
        for case in cases:
            assert case['reference_passed'] and case['rtl_passed']
            for key in ['elf', 'rtl_trace']:
                assert sha(ROOT / case[key]) == case[key + '_sha256']
            dest = folder / case['name']
            dest.mkdir(parents=True, exist_ok=True)
            trace = dest / 'sail_events.csv'
            run, text = sim.run([ROOT / driver['binary'], '--config', config,
                '--commit-csv', trace, '--inst-limit', '1000000', ROOT / case['elf']], dest / 'sail.log', 180)
            assert 'PASS Sail HTIF' in text
            reference, actual = read_csv(trace), read_csv(ROOT / case['rtl_trace'])
            compared, mismatch = compare(reference, actual)
            row = dict(name=case['name'], passed=mismatch is None, compared=compared,
                elf_sha256=case['elf_sha256'], rtl_trace_sha256=case['rtl_trace_sha256'],
                sail_trace=trace.relative_to(ROOT).as_posix(), sail_trace_sha256=sha(trace),
                run=run, first_mismatch=mismatch,
                interrupts=sum(r['interrupt'] == '1' for r in reference),
                wfi=sum(int(r['instruction'], 16) == 0x10500073 for r in reference))
            if mismatch is None and case['name'] in ['rv64mi/illegal', 'rv64si/wfi']:
                # Remove precisely the event omitted by the legacy callback.
                selector = (lambda r: r['interrupt'] == '1') if case['name'].endswith('illegal') else (
                    lambda r: int(r['instruction'], 16) == 0x10500073)
                removed = next(i for i, r in enumerate(reference) if selector(r))
                corrupted = reference[:removed] + reference[removed + 1:]
                rejected_index, rejected = compare(corrupted, actual)
                assert rejected is not None and rejected_index == removed
                negative = dest / 'omitted_event.csv'
                with negative.open('w', newline='', encoding='utf-8') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(reference[0]))
                    writer.writeheader()
                    writer.writerows(corrupted)
                row['omission_control'] = dict(rejected=True, index=removed,
                    trace=negative.relative_to(ROOT).as_posix(), trace_sha256=sha(negative), mismatch=rejected)
            result['cases'].append(row)
            dump(folder / 'report.json', result)
            print('PASS' if row['passed'] else 'DIFF', 'privileged event trace', case['name'], compared, flush=True)
    result['passed'] = all(c['passed'] for c in result['cases'])
    result['retirements_compared'] = sum(c['compared'] for c in result['cases'])
    result['omission_controls'] = sum('omission_control' in c for c in result['cases'])
    dump(folder / 'report.json', result)
    assert result['passed'], [c['name'] for c in result['cases'] if not c['passed']]
    assert result['omission_controls'] == 2
    print('PASS privileged event comparison:', len(cases), 'ELFs,', result['retirements_compared'],
          'events; 2 omitted-event controls rejected', flush=True)


if __name__ == '__main__':
    main()

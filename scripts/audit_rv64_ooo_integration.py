"""Reconstruct RV64 issue/execute/retire evidence from actual pipeline CSV."""
from collections import Counter
import csv
import json

from sim_runner import ROOT, dump, sha, source_inputs
from run_rv64_ooo_integration import BANK_WORDS, verify_cache_pairs


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    folder = ROOT / 'out/rva23/rv64_ooo'
    report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
    assert report['passed'] and report['model']['passed']
    assert report['generator_sha256'] == sha(ROOT / 'scripts/run_rv64_ooo_integration.py')
    model = report['model']
    required = source_inputs((ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines())
    assert all(model['inputs'].get(p) == digest for p, digest in required.items())
    for path, digest in {**model['inputs'], **report['runtime_inputs']}.items():
        assert sha(ROOT / path) == digest, path
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    for filename, key in [('test.S','source'), ('test.elf','elf'), ('pipeline.csv','pipeline'), ('commit.csv','trace')]:
        assert sha(folder / filename) == report[key + '_sha256']
    for stage in ['compile','run']:
        run = report[stage]
        assert run['passed'] and run['exit_code'] == 0
        assert sha(ROOT / run['log']) == run['log_sha256']
    symbols, coverage = report['symbols'], report['coverage']
    start, first, end = symbols['ooo_div'], symbols['ooo_first'], symbols['ooo_end']
    dependent = symbols['ooo_dep']
    events = rows(folder / 'pipeline.csv')
    issue, execute, retire = [[r for r in events if r['event'] == event] for event in ['issue','execute','retire']]
    assert len(issue) == len(retire) == 10 and len(execute) == 9
    expected = list(range(start, end, 4))
    assert sorted(int(r['pc'],16) for r in issue) == expected
    assert sorted(int(r['pc'],16) for r in execute) == expected[1:]
    assert [int(r['pc'],16) for r in retire] == expected
    issue_by_pc = {int(r['pc'],16):r for r in issue}
    execute_by_pc = {int(r['pc'],16):r for r in execute}
    retire_by_pc = {int(r['pc'],16):r for r in retire}
    assert all(issue_by_pc[pc]['sequence'] == retire_by_pc[pc]['sequence'] for pc in expected)
    for pc in expected[1:]:
        assert issue_by_pc[pc]['sequence'] == execute_by_pc[pc]['sequence']
        assert int(issue_by_pc[pc]['cycle']) < int(execute_by_pc[pc]['cycle']) < int(retire_by_pc[pc]['cycle'])
    # Independently reconstruct pair counts rather than trusting PASS text.
    dual_issue = sum(n == 2 for n in Counter(int(r['cycle']) for r in issue if first <= int(r['pc'],16) < end).values())
    dual_execute = sum(n == 2 for n in Counter(int(r['cycle']) for r in execute).values())
    dual_retire = sum(n == 2 for n in Counter(int(r['cycle']) for r in retire).values())
    assert (dual_issue,dual_execute,dual_retire) == tuple(coverage[k] for k in ['dual_issue','dual_execute','dual_retire'])
    assert min(dual_issue,dual_execute,dual_retire) > 0
    div_cycle = int(issue_by_pc[start]['cycle'])
    dep_cycle = int(issue_by_pc[dependent]['cycle'])
    first_cycle = min(int(r['cycle']) for r in issue if first <= int(r['pc'],16) < end)
    assert div_cycle < first_cycle < dep_cycle
    assert (div_cycle,first_cycle,dep_cycle) == tuple(coverage[k] for k in ['div_issue_cycle','first_young_issue_cycle','dependent_issue_cycle'])
    assert min(int(r['cycle']) for r in execute if first <= int(r['pc'],16) < end) < int(execute_by_pc[dependent]['cycle'])
    commits = rows(folder / 'commit.csv')
    architectural = [r for r in commits if start <= int(r['pc'],16) < end]
    assert len(architectural) == 10
    for row, oracle, register in zip(architectural,report['expected_writebacks'],range(8,18)):
        assert row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0'
        assert int(row['rd']) == register and int(row['wdata'],16) == int(oracle['value'],16)
    bank_rows = [r for r in commits if int(r['pc'], 16) in report['bank_load_pcs']]
    assert [int(r['pc'], 16) for r in bank_rows] == report['bank_load_pcs'] * 8
    assert all(r['trap'] == '0' and r['rd_write'] == '1' and r['rd_fp'] == '0' for r in bank_rows)
    assert [int(r['wdata'], 16) for r in bank_rows] == list(BANK_WORDS.values()) * 8
    output = (ROOT / report['run']['log']).read_text(encoding='utf-8')
    cache_banks = verify_cache_pairs(output)
    assert cache_banks == report['cache_banks']
    dump(folder / 'audit.json', dict(passed=True, complete_profile_validation=False,
        scope=report['scope'], audit_sha256=sha(__file__), report_sha256=sha(folder / 'report.json'),
        coverage=coverage, cache_banks=cache_banks, verified_bank_loads=len(bank_rows),
        verified_architectural_results=10, verified_pipeline_events=len(events)))
    print('PASS current RV64 OoO and cache bank evidence:', cache_banks)


if __name__ == '__main__':
    main()

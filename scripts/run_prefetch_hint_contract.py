"""Native Zicbop field sweep using the immutable RV64I snapshot oracle."""
import argparse
import json

from audit_hv_sail_fixture import check_fixture
from run_hv_sail_fixture import run_fixture
from run_rv64i_hint_contract import DEPENDENCIES as HINT_DEPENDENCIES
from run_rv64i_hint_contract import fixture, verifier
from sim_runner import ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/prefetch_hint_contract'
DEPENDENCIES = [*HINT_DEPENDENCIES, 'scripts/run_rv64i_hint_contract.py']
BATCH = 128


def cases():
    plan = []
    for name, selector in [('prefetch.i', 0), ('prefetch.r', 1), ('prefetch.w', 3)]:
        # Cover all signed 12-bit, 32-byte-multiple offsets with selected bases,
        # then every base with the minimum, zero and maximum offset.
        pairs = {(base, offset) for base in (0, 8, 31) for offset in range(-2048, 2048, 32)}
        pairs |= {(base, offset) for base in range(32) for offset in (-2048, 0, 2016)}
        for base, offset in sorted(pairs):
            word = (offset & 0xfe0) << 20 | selector << 20 | base << 15 | 6 << 12 | 0x13
            assert word & 0x7f == 0x13 and (word >> 7) & 31 == 0 and (word >> 12) & 7 == 6
            assert (word >> 20) & 31 == selector
            encoded = (word >> 20) & 0xfe0
            assert (encoded - 4096 if encoded & 2048 else encoded) == offset
            plan.append(dict(name=name, word=word))
    assert len(plan) == 1413 and len({case['word'] for case in plan}) == len(plan)
    return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    plan = cases()
    batches = [plan[start:start + BATCH] for start in range(0, len(plan), BATCH)]
    FOLDER.mkdir(parents=True, exist_ok=True)
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        scope='M-mode Zicbop ignored-hint policy: three forms, every offset with selected base registers and every base with selected offsets; full GPR/FPR snapshots, FCSR/guards and exact PC. Not all encoding combinations, privileges, bus side effects, real prefetch performance or universal ordering proof',
        inputs=source_inputs(DEPENDENCIES), probes=len(plan), cases=[])
    if args.check:
        saved = json.loads((FOLDER / 'report.json').read_bytes())
        assert saved['passed'] and saved['generator_sha256'] == top['generator_sha256']
        assert saved['inputs'] == top['inputs'] and saved['probes'] == len(plan)
        assert len(saved['cases']) == len(batches)
    else:
        dump(FOLDER / 'report.json', top)
    for index, batch in enumerate(batches):
        folder = FOLDER / str(index)
        folder.mkdir(exist_ok=True)
        source, verify = folder / 'test.S', verifier(batch, index, folder)
        if args.check:
            outcome = check_fixture(folder, __file__, fixture(batch, index), verify)
            old = saved['cases'][index]
            assert old['index'] == index and old['report_sha256'] == sha(folder / 'report.json')
            assert old['outcomes'] == outcome
        else:
            source.write_text(fixture(batch, index), encoding='utf-8')
            outcome = run_fixture(source, folder, __file__, verify,
                source_dependencies=DEPENDENCIES, timeout_cycles=3000000)
        top['cases'].append(dict(index=index, report_sha256=sha(folder / 'report.json'), outcomes=outcome))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS native Zicbop', index, outcome['probes'], 'probes;', outcome['matched_events'],
            'Sail/RTL events;', len(outcome['rejected_mutations']), 'rejected mutations', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

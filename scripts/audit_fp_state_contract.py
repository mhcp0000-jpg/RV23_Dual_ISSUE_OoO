"""Bind existing full-H/V FS/SD, FS-Off and reserved-rm execution evidence."""
import copy
import json

from run_sail_event_comparison import read_csv
from sim_runner import ROOT, dump, sha, source_inputs


SOURCE = 'sw/tests/rv64_fp_state.S'
TRAPS = [0x02007153, 0x00043107, 0x00143027, 0xe20002d3,
         0x003022f3, 0x02005153, 0x02007153]


def inspect(rows):
    payload = [row for row in rows if int(row['pc'], 16) >= 0x80000000]
    reads = [row for row in payload if int(row['instruction'], 16) & 127 == 0x73
             and int(row['instruction'], 16) >> 20 == 0x300
             and row['rd_write'] == '1' and int(row['rd']) != 0]
    assert len(reads) == 5
    states = [1, 3, 2, 3, 3]
    for row, expected in zip(reads, states):
        assert row['trap'] == '0' and row['rd_fp'] == '0'
        value = int(row['wdata'], 16)
        assert (value >> 9) & 3 == 0 and (value >> 15) & 3 == 0
        assert (value >> 13) & 3 == expected and value >> 63 == (expected == 3), row
    traps = [row for row in payload if row['trap'] == '1']
    assert len(traps) == len(TRAPS)
    for row, word in zip(traps, TRAPS):
        assert int(row['instruction'], 16) == word and int(row['cause']) == 2
        assert int(row['tval'], 16) == word and row['rd_write'] == '0', row
    flags = [int(row['wdata'], 16) for row in payload if row['trap'] == '0'
        and int(row['instruction'], 16) & 127 == 0x73
        and int(row['instruction'], 16) >> 20 == 1
        and row['rd_write'] == '1' and int(row['rd']) != 0]
    assert flags == [16, 0], flags
    compressed = sum(int(row['instruction'], 16) & 3 != 3 for row in payload)
    assert compressed >= 6
    return dict(mstatus_fs_states=states, precise_traps=len(traps),
        off_traps=5, reserved_rounding_traps=2, fflags_reads=flags, compressed_retirements=compressed)


def main():
    path = ROOT / 'out/rva23/profile_hypervisor_replay/report.json'
    replay = json.loads(path.read_bytes())
    assert replay['passed'] and replay['generator_sha256'] == sha(ROOT / 'scripts/run_profile_hypervisor_replay.py')
    model = replay['model']
    assert source_inputs(model['inputs']) == model['inputs']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1', '-GHAS_D=1'} <= set(model['params'])
    assert source_inputs(replay['runtime_inputs']) == replay['runtime_inputs']
    case = next(case for case in replay['cases'] if case['name'] == 'fp_state')
    assert case['passed']
    artifacts = {}
    for key in ('original_report', 'elf', 'baseline_trace', 'baseline_log', 'trace'):
        assert sha(ROOT / case[key]) == case[key + '_sha256']
        artifacts[case[key]] = case[key + '_sha256']
    original = json.loads((ROOT / case['original_report']).read_bytes())
    assert original['passed'] and original['source_sha256'] == sha(ROOT / SOURCE)
    assert original['generator_sha256'] == sha(ROOT / 'scripts/run_fp_state_integration.py')
    assert original['elf_sha256'] == case['elf_sha256']
    run = case['run']
    assert run['passed'] and run['exit_code'] == 0 and sha(ROOT / run['log']) == run['log_sha256']
    artifacts[run['log']] = run['log_sha256']
    rows = read_csv(ROOT / case['trace'])
    outcomes = inspect(rows)
    controls = []
    selections = [('fs', i) for i in range(5)] + [('cause', i) for i in range(7)] + [('tval', i) for i in range(7)]
    for kind, index in selections:
        broken = copy.deepcopy(rows)
        if kind == 'fs':
            candidates = [row for row in broken if int(row['pc'], 16) >= 0x80000000
                and int(row['instruction'], 16) & 127 == 0x73
                and int(row['instruction'], 16) >> 20 == 0x300
                and row['rd_write'] == '1' and int(row['rd']) != 0]
            candidates[index]['wdata'] = f"{int(candidates[index]['wdata'], 16) ^ (1 << 13):016x}"
        else:
            row = [row for row in broken if int(row['pc'], 16) >= 0x80000000 and row['trap'] == '1'][index]
            row[kind] = '3' if kind == 'cause' else f"{int(row['tval'], 16) ^ 1:016x}"
        try:
            inspect(broken)
        except AssertionError:
            controls.append(dict(kind=kind, index=index))
        else:
            raise AssertionError(f'Incorrect FP state {kind} {index} accepted')
    dump(ROOT / 'out/rva23/fp_state_contract_audit.json', dict(
        passed=True, complete_profile_validation=False,
        scope='Existing full-H/V M-mode FS/SD policy and seven precise traps; precise Clean tracking is implementation policy, not a universal ISA requirement; guest FS/privilege combinations separate',
        base_report_sha256=sha(path), model_binary_sha256=model['binary_sha256'],
        audit_inputs=source_inputs([SOURCE, 'scripts/audit_fp_state_contract.py',
            'scripts/run_sail_event_comparison.py', 'scripts/run_fp_state_integration.py', 'scripts/sim_runner.py']),
        artifacts=artifacts, outcomes=outcomes, rejected_mutations=controls))
    print('PASS current H/V FS/SD and seven precise traps; 19 rejected mutations', outcomes)


if __name__ == '__main__':
    main()

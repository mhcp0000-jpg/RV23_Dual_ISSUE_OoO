"""Recheck current-source scalar/vector ordering evidence and witness controls.

This audits existing RTL executions; negative controls mutate recorded witnesses,
not hardware. It does not establish complete RVWMO or profile compliance.
"""
import importlib
import json
import re

import run_fence_order as fence
import run_svpbmt_alias_order as pbmt
import run_vector_branch_order as branch
from sim_runner import ROOT, dump, sha, source_inputs


def reject(name, check, controls):
    try:
        check()
    except AssertionError:
        controls.append(name)
    else:
        raise AssertionError(f'Incorrect ordering witness accepted: {name}')


def main():
    reports, outcomes, controls = {}, {}, []
    drivers = ('scalar_vector_memory', 'indexed_memory_restart',
               'svpbmt_alias_order', 'vector_irq_boundary')
    for name in drivers:
        folder = ROOT / 'out/rva23' / name
        report = folder / 'report.json'
        record = json.loads(report.read_text(encoding='utf-8'))
        assert record['passed'] is True
        model = record['model']
        if name == 'vector_irq_boundary':
            assert model['top'] == 'rv23_vector_irq_tb'
            wrapper = 'tb/rv23_vector_irq_tb.sv'
            assert wrapper in model['inputs']
            text = (ROOT / wrapper).read_text(encoding='utf-8')
            assert all(setting in text for setting in ('.XLEN(64)', '.HAS_H(1)', '.HAS_V(1)'))
        else:
            assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(model['params'])
        inputs = {**model['inputs'], **record['runtime_inputs'],
                  model['binary']: model['binary_sha256']}
        assert source_inputs(inputs) == inputs
        driver = importlib.import_module('run_' + name)
        assert sha(driver.__file__) == record['generator_sha256']
        for filename, key in [('test.elf', 'elf_sha256'), ('commit.csv', 'trace_sha256'),
                              ('sail.csv', 'sail_trace_sha256')]:
            if key in record:
                assert sha(folder / filename) == record[key], (name, filename)
        for key in ('compile', 'run', 'sail', 'bus_run'):
            if key in record:
                step = record[key]
                assert step['passed'] and step['exit_code'] == 0, (name, key)
                assert sha(ROOT / step['log']) == step['log_sha256']
        if name == 'vector_irq_boundary':
            log = (ROOT / record['run']['log']).read_text(encoding='utf-8')
            observed = driver.verify(folder / 'commit.csv', log)
            # Force vector retirement before the last accepted store element.
            broken, count = re.subn(r'(last=)(\d+)( retire=)(\d+)',
                                    lambda m: m[1] + m[2] + m[3] + str(int(m[2]) - 1), log)
            assert count == 1
            reject('vector_retire_before_last_store',
                   lambda: driver.verify(folder / 'commit.csv', broken), controls)
            broken = log.replace('PLIC CLAIM ORDER vector=2 scalar=2',
                                 'PLIC CLAIM ORDER vector=1 scalar=2')
            assert broken != log
            reject('missing_vector_mmio_claim',
                   lambda: driver.verify(folder / 'commit.csv', broken), controls)
        else:
            observed = driver.verify_traces(folder / 'sail.csv', folder / 'commit.csv')
        assert observed == record['outcomes'], name
        outcomes[name] = observed
        if name == 'svpbmt_alias_order':
            log = (ROOT / record['bus_run']['log']).read_text(encoding='utf-8')
            assert pbmt.verify_bus(log) == record['bus']
            # Remove a real zero-stride IO read, preserving all other bus traffic.
            lines = log.splitlines(keepends=True)
            candidates = [i for i, line in enumerate(lines)
                          if 'AR=1/1' in line and
                          re.search(r'addr=0*' + f'{pbmt.ZERO_STRIDE_LOAD:x}' + r'\b', line)]
            assert candidates
            del lines[candidates[0]]
            reject('missing_zero_stride_io_read',
                   lambda: pbmt.verify_bus(''.join(lines)), controls)
        reports[report.relative_to(ROOT).as_posix()] = sha(report)

    folder = ROOT / 'out/rva23/fence_order'
    report = folder / 'report.json'
    record = json.loads(report.read_text(encoding='utf-8'))
    fence.check(record, source_inputs(record['model']['inputs']))
    log = (ROOT / record['run']['log']).read_text(encoding='utf-8')
    broken, count = re.subn(r'^FENCE_ORDER \d+ debug_write [\da-f]+\r?\n', '', log, flags=re.M)
    assert count == 1
    reject('missing_concurrent_debug_write', lambda: fence.verify(broken), controls)
    outcomes['fence_order'] = record['coverage']
    reports[report.relative_to(ROOT).as_posix()] = sha(report)
    outcomes['vector_branch_order'] = branch.check()
    report = branch.FOLDER / 'report.json'
    reports[report.relative_to(ROOT).as_posix()] = sha(report)
    controls.append('missing_speculative_vector_dispatch')
    dump(ROOT / 'out/rva23/scalar_vector_order_audit.json', dict(
        passed=True, complete_profile_validation=False,
        scope='Existing directed RTL executions: shared memory, precise restart, PBMT IO, interrupts, FENCE/CBO and speculative vector squash; no exhaustive RVWMO proof',
        reports=reports, outcomes=outcomes, witness_negative_controls=controls,
        audit_sha256=sha(__file__)))
    print('PASS current-source scalar/vector ordering: six execution reports, five rejected witness mutations')


if __name__ == '__main__':
    main()

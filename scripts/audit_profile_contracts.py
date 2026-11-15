"""Run or audit directed profile contract tests against the current RTL."""
import argparse
import csv
import itertools
import json
import re
import subprocess
import sys

import run_cbo_permission_matrix as cbo_matrix
import run_guest_interrupt_priority as guest_interrupt_priority
import run_guest_pointer_mask_faults as pointer_mask
import run_guest_superpages as guest_superpages
import run_guest_stateen as guest_stateen
import run_guest_timer_wrap as guest_timer
import run_hlvx_permissions as hlvx_permissions
import run_interrupt_csr_boundary as interrupt_boundary
from run_guest_wrs_timeout import CASES as WRS_CASES, MARKER as WRS_MARKER
from run_guest_wrs_timeout import fixture as wrs_fixture, verify_trace as verify_wrs_trace
from run_hpm_mode_filters import (
    MARKER as HPM_MARKER,
    OVERFLOW_MARKER,
    fixture as hpm_fixture,
    overflow_fixture,
    trace_modes,
    trace_overflow,
)
import run_sv39x4_root as gstage_root
import run_vector_overlap as vector_overlap
import run_zvbb_native as zvbb_native
import run_wrs_debug_wake as wrs_debug
from sim_runner import ROOT, dump, sha, source_inputs


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rerun', action='store_true',
                        help='Execute the directed contract tests before auditing their artifacts')
    args = parser.parse_args()
    rtl = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines()
    files = rtl + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']
    inputs = source_inputs(files)
    results = {}

    def audit(folder, driver, *, options=(), source=None, wrapper=None):
        if args.rerun:
            print('RUN', driver, *options, flush=True)
            subprocess.run([sys.executable, str(ROOT / 'scripts' / driver), *options],
                           cwd=ROOT, check=True)
        report = read(folder + '/report.json')
        assert report['passed'] and report['generator_sha256'] == sha(ROOT / 'scripts' / driver)
        model = report['model']
        assert model['inputs'] == (source_inputs(files + [wrapper]) if wrapper else inputs)
        assert sha(ROOT / model['binary']) == model['binary_sha256']
        if wrapper:
            assert model['top'] == (ROOT / wrapper).stem
        else:
            assert all(p in model['params'] for p in ['-GHAS_H=1', '-GHAS_V=1', '-GXLEN=64'])
        assert sha(ROOT / source if source else ROOT / folder / 'test.S') == report['source_sha256']
        for artifact, key in [('test.elf', 'elf'), ('commit.csv', 'trace')]:
            assert sha(ROOT / folder / artifact) == report[key + '_sha256']
        for path, digest in report.get('runtime_inputs', {}).items():
            assert sha(ROOT / path) == digest
        for phase in ['compile', 'run']:
            run = report[phase]
            assert run['passed'] and run['exit_code'] == 0
            assert sha(ROOT / run['log']) == run['log_sha256']
        results[folder] = sha(ROOT / folder / 'report.json')
        return report

    def audit_testbench(path, driver, top, sources):
        if args.rerun:
            print('RUN', driver, flush=True)
            subprocess.run([sys.executable, str(ROOT / 'scripts' / driver)], cwd=ROOT, check=True)
        model = read(path)
        run = model['run']
        assert model['passed'] and model['top'] == top and not model['params']
        assert model['inputs'] == source_inputs(sources + [f'tb/{top}.sv'])
        assert sha(ROOT / model['binary']) == model['binary_sha256']
        assert run['passed'] and run['exit_code'] == 0 and sha(ROOT / run['log']) == run['log_sha256']
        results[path] = sha(ROOT / path)
        return (ROOT / run['log']).read_text(encoding='utf-8', errors='replace')

    counter_cases = 0
    for form in ['read', 'high', 'write_zero']:
        folder = 'out/rva23/counter_permission_matrix/' + form
        report = audit(folder, 'run_counter_permission_matrix.py', options=('--form', form))
        assert sha(ROOT / folder / 'cases.json') == report['cases_sha256']
        cases = read(folder + '/cases.json')
        expected = set(itertools.product(['M', 'HS', 'VS', 'U', 'VU'],
                                        [0, 1, 2, 3, 4, 5, 6, 31], range(2), range(2), range(2)))
        actual = {(c['mode'], c['index'], c['mg'], c['hg'], c['sg']) for c in cases}
        assert len(cases) == report['case_count'] == 320 and actual == expected
        assert all(c['form'] == form for c in cases)
        counter_cases += len(cases)
    folder = 'out/rva23/hpm_mode_filters'
    hpm = audit(folder, 'run_hpm_mode_filters.py')
    assert (ROOT / folder / 'test.S').read_text(encoding='utf-8') == hpm_fixture()
    assert hpm['modes'] == trace_modes(ROOT / folder / 'commit.csv')
    hpm_log = (ROOT / hpm['run']['log']).read_text(encoding='utf-8', errors='replace')
    assert 'PASS rv32_program_tb' in hpm_log and f'data={HPM_MARKER}' in hpm_log
    folder = 'out/rva23/hpm_machine_overflow'
    overflow = audit(folder, 'run_hpm_mode_filters.py', options=('--machine-overflow',))
    assert (ROOT / folder / 'test.S').read_text(encoding='utf-8') == overflow_fixture()
    assert overflow['traps'] == trace_overflow(ROOT / folder / 'commit.csv')
    overflow_log = (ROOT / overflow['run']['log']).read_text(encoding='utf-8', errors='replace')
    assert 'PASS rv32_program_tb' in overflow_log and f'data={OVERFLOW_MARKER}' in overflow_log
    folder = 'out/rva23/guest_wrs_timeout'
    wrs = audit(folder, 'run_guest_wrs_timeout.py')
    assert wrs['cases'] == [list(case) for case in WRS_CASES]
    assert (ROOT / folder / 'test.S').read_text(encoding='utf-8') == wrs_fixture()
    for key, value in verify_wrs_trace(ROOT / folder / 'commit.csv').items():
        assert wrs[key] == value, key
    wrs_log = (ROOT / wrs['run']['log']).read_text(encoding='utf-8', errors='replace')
    assert 'PASS rv32_program_tb' in wrs_log and f'data={WRS_MARKER}' in wrs_log
    wake = audit(wrs_debug.FOLDER, 'run_wrs_debug_wake.py',
                 source=wrs_debug.SOURCE, wrapper=wrs_debug.TESTBENCH)
    wake_log = (ROOT / wake['run']['log']).read_text(encoding='utf-8', errors='replace')
    assert all(marker in wake_log for marker in (
        wrs_debug.WITNESS, wrs_debug.INTERFERENCE_WITNESS, wrs_debug.MARKER, 'PASS rv32_program_tb'))
    assert (wake['outcomes'], wake['interference']) == wrs_debug.verify_trace(
        ROOT / wrs_debug.FOLDER / 'commit.csv')
    folder = ROOT / pointer_mask.FOLDER
    masked = audit(pointer_mask.FOLDER, 'run_guest_pointer_mask_faults.py')
    assert '-GHAS_SSNPM=1' in masked['model']['params']
    assert (folder / 'test.S').read_text(encoding='utf-8') == pointer_mask.fixture()
    assert masked['traps'] == pointer_mask.verify_trace(folder / 'commit.csv')
    masked_log = (ROOT / masked['run']['log']).read_text(encoding='utf-8', errors='replace')
    assert pointer_mask.MARKER in masked_log and '[host-finish code=0]' in masked_log
    control = masked['disabled']
    assert sha(folder / 'disabled.elf') == control['elf_sha256']
    assert sha(folder / 'disabled.csv') == control['trace_sha256']
    assert control['traps'] == pointer_mask.verify_control(folder / 'disabled.csv')
    for phase in ('compile', 'run'):
        run = control[phase]
        assert run['passed'] and run['exit_code'] == 0
        assert sha(ROOT / run['log']) == run['log_sha256']
    control_log = (ROOT / control['run']['log']).read_text(encoding='utf-8', errors='replace')
    assert '[host-finish code=1]' in control_log and pointer_mask.MARKER not in control_log
    vu_folder = 'out/rva23/hypervisor_vector_faults_vu'
    vu = audit(vu_folder, 'run_hypervisor_vector_faults.py', options=('--vu',))
    vu_log = (ROOT / vu['run']['log']).read_text(encoding='utf-8', errors='replace')
    assert 'data=0x48595035' in vu_log and '[host-finish code=0]' in vu_log
    with (ROOT / vu_folder / 'commit.csv').open(newline='') as stream:
        vu_rows = list(csv.DictReader(stream))
    vu_traps = [row for row in vu_rows if row['trap'] == '1' and int(row['pc'], 16) >= 0x40000000]
    assert vu_traps == vu['traps']
    assert [int(row['cause']) for row in vu_traps] == [23, 8, 21, 8]
    assert [int(row['tval'], 16) for row in vu_traps] == [0x400a4000, 0, 0x400a4000, 0]
    vu_retries = []
    for fault, next_trap in zip(vu_traps[::2], vu_traps[1::2]):
        retry, = (row for row in vu_rows if row['trap'] == '0' and row['pc'] == fault['pc'] and
                  row['instruction'] == fault['instruction'] and
                  int(fault['order']) < int(row['order']) < int(next_trap['order']))
        vu_retries.append(retry)
    assert vu_retries == vu['retries']
    folder = ROOT / cbo_matrix.FOLDER
    cbo = audit(cbo_matrix.FOLDER, 'run_cbo_permission_matrix.py')
    assert '-GHAS_CBO=1' in cbo['model']['params']
    assert cbo['cases'] == cbo_matrix.cases() and len(cbo['cases']) == 255
    assert (folder / 'test.S').read_text(encoding='utf-8') == cbo_matrix.fixture(cbo['cases'])
    assert cbo['outcomes'] == cbo_matrix.verify_trace(folder / 'commit.csv', cbo['cases'])
    cbo_log = (ROOT / cbo['run']['log']).read_text(encoding='utf-8', errors='replace')
    assert cbo_matrix.MARKER in cbo_log and '[host-finish code=0]' in cbo_log
    folder = ROOT / interrupt_boundary.FOLDER
    interrupt = audit(interrupt_boundary.FOLDER, 'run_interrupt_csr_boundary.py')
    assert (folder / 'test.S').read_text(encoding='utf-8') == interrupt_boundary.fixture()
    assert interrupt['outcomes'] == interrupt_boundary.verify_trace(folder / 'commit.csv')
    interrupt_log = (ROOT / interrupt['run']['log']).read_text(encoding='utf-8', errors='replace')
    assert interrupt_boundary.MARKER in interrupt_log and '[host-finish code=0]' in interrupt_log

    timer = audit(guest_timer.FOLDER, 'run_guest_timer_wrap.py', source=guest_timer.SOURCE)
    timer_outcomes = guest_timer.verify_trace(ROOT / guest_timer.FOLDER / 'commit.csv')
    assert timer_outcomes == timer['outcomes']
    timer_log = (ROOT / timer['run']['log']).read_text(encoding='utf-8')
    assert guest_timer.MARKER in timer_log and '[host-finish code=0]' in timer_log

    stateen = audit(guest_stateen.FOLDER, 'run_guest_stateen.py', source=guest_stateen.SOURCE)
    stateen_outcomes = guest_stateen.verify_trace(ROOT / guest_stateen.FOLDER / 'commit.csv')
    assert stateen_outcomes == stateen['outcomes']
    stateen_log = (ROOT / stateen['run']['log']).read_text(encoding='utf-8')
    assert guest_stateen.MARKER in stateen_log and '[host-finish code=0]' in stateen_log

    priority = audit(guest_interrupt_priority.FOLDER, 'run_guest_interrupt_priority.py',
                     source=guest_interrupt_priority.SOURCE)
    priority_outcomes = guest_interrupt_priority.verify_trace(ROOT / guest_interrupt_priority.FOLDER / 'commit.csv')
    assert priority_outcomes == priority['outcomes']
    priority_log = (ROOT / priority['run']['log']).read_text(encoding='utf-8')
    assert guest_interrupt_priority.MARKER in priority_log and '[host-finish code=0]' in priority_log
    folder = 'out/rva23/rv64_platform_contract'
    platform = audit(folder, 'run_rv64_platform_contract.py')
    platform_log = (ROOT / platform['run']['log']).read_text(encoding='utf-8', errors='replace')
    assert all(marker in platform_log for marker in (
        'PASS rv32_program_tb', 'data=0x52563634', 'NATIVE DEBUG PASS halt/drain/read/write/resume'))
    with (ROOT / folder / 'commit.csv').open(newline='') as stream:
        traps = [int(row['cause']) for row in csv.DictReader(stream)
                 if row['trap'] == '1' and int(row['pc'], 16) >= 0x80000000]
    assert traps == platform['traps'] == [3, 7, 11, 5, 9]
    folder = ROOT / gstage_root.FOLDER
    root = audit(gstage_root.FOLDER, 'run_sv39x4_root.py')
    assert '-GHAS_MMU=1' in root['model']['params']
    assert root['probes'] == [list(probe) for probe in gstage_root.PROBES]
    assert root['remaps'] == [list(remap) for remap in gstage_root.REMAPS]
    assert root['vs_remap'] == {'gva': gstage_root.VS_GVA,
                                'gpas': [gstage_root.PROBES[index][0] for index in gstage_root.VS_GPA_INDICES]}
    assert (folder / 'test.S').read_text(encoding='utf-8') == gstage_root.fixture()
    assert root['traps'] == gstage_root.verify_trace(folder / 'commit.csv')
    root_log = (ROOT / root['run']['log']).read_text(encoding='utf-8', errors='replace')
    assert gstage_root.MARKER in root_log and '[host-finish code=0]' in root_log
    report = audit('out/rva23/lrsc_progress', 'run_lrsc_progress.py')
    placements = {(c['width'], c['data_offset'], c['instruction_line_offset']) for c in report['cases']}
    expected = {(width, offset, position) for width in [32, 64]
                for offset in range(0, 64, width // 8) for position in [0, 32, 62]}
    assert len(report['cases']) == 72 and placements == expected
    assert report['successful_updates'] == 1152
    assert report['lr_retirements'] == report['sc_retirements'] >= 1152
    folder = 'out/rva23/profile_csr_geometry'
    geometry = audit(folder, 'run_profile_csr_geometry.py')
    assert sha(ROOT / folder / 'cases.json') == geometry['cases_sha256']
    cases = read(folder + '/cases.json')
    assert len(cases) == geometry['case_count'] == 279 and geometry['vector_bases'] == 76
    assert {c['csr'] for c in cases} == ({'stvec', 'vstvec', 'satp', 'vsatp', 'hgatp', 'sstatus', 'vsstatus'} |
                                      {f'{prefix}stateen{n}' for prefix in ['s', 'h'] for n in range(4)})
    folder = 'out/rva23/split_fetch_faults'
    split = audit(folder, 'run_split_fetch_faults.py')
    assert sha(ROOT / folder / 'cases.json') == split['cases_sha256']
    cases = read(folder + '/cases.json')
    expected = {(m,t,k) for m,t in [('HS','M'),('HS','HS'),('VS','M'),('VS','HS'),('VS','VS')]
                for k in ['page','access']} | {('VS','M','gstage'),('VS','HS','gstage')}
    assert split['case_count'] == len(cases) == 12
    assert {(c['mode'],c['target'],c['kind']) for c in cases} == expected
    assert len(split['traps']) == 24
    for case, trap in zip(cases,split['traps'][::2]):
        assert int(trap['pc'],16) == case['instruction_pc'] == 0x40000ffe
        assert int(trap['tval'],16) == case['fault_address'] == 0x40001000
        assert int(trap['cause']) == case['cause'] == {'page':12,'access':1,'gstage':20}[case['kind']]

    overlap = audit(vector_overlap.FOLDER, 'run_vector_overlap.py', source=vector_overlap.SOURCE)
    outcomes = vector_overlap.verify_trace(ROOT / vector_overlap.FOLDER / 'commit.csv')
    assert outcomes == overlap['outcomes']

    superpages = audit(guest_superpages.FOLDER, 'run_guest_superpages.py')
    superpage_folder = ROOT / guest_superpages.FOLDER
    assert (superpage_folder / 'test.S').read_text(encoding='utf-8') == guest_superpages.fixture()
    superpage_results = guest_superpages.verify_trace(superpage_folder / 'commit.csv')
    assert superpage_results == superpages['outcomes']

    hlvx = audit(hlvx_permissions.FOLDER, 'run_hlvx_permissions.py')
    assert hlvx['model_sha256'] == sha(ROOT / 'out/rva23/hypervisor_integration/model.json')
    permission_cases = list(hlvx_permissions.permission_cases())
    assert len(hlvx['cases']) == len(permission_cases) == 35
    expected_traps = []
    for case, (vs, g, hs_mxr, vs_mxr, op, offset, cause) in zip(hlvx['cases'], permission_cases):
        address = 0x400a0000 + offset
        htval = (0x200a0000 + offset) >> 2 if cause == 21 else 0
        assert case == dict(vs=vs, g=g, hs_mxr=hs_mxr, vs_mxr=vs_mxr, op=op,
                            address=address, cause=cause, htval=htval)
        if cause:
            expected_traps.append([cause, address])
    assert hlvx['traps'] == expected_traps == hlvx_permissions.trap_trace(ROOT / hlvx_permissions.FOLDER / 'commit.csv')
    assert hlvx_permissions.MARKER in (ROOT / hlvx['run']['log']).read_text(encoding='utf-8')

    zvbb = audit(zvbb_native.FOLDER, 'run_zvbb_native.py')
    zvbb_folder = ROOT / zvbb_native.FOLDER
    zvbb_source, zvbb_cases = zvbb_native.fixture()
    assert (zvbb_folder / 'test.S').read_text(encoding='utf-8') == zvbb_source
    zvbb_trace = zvbb_folder / 'commit.csv'
    zvbb_outcomes = zvbb_native.verify_trace(zvbb_trace, zvbb_cases)
    assert zvbb_outcomes == zvbb['outcomes'] == dict(forms=16, cases=183, destination_words=1464)
    encodings = [entry for entry in read(zvbb_native.TABLE)['instructions'] if entry['extension'] == 'ZVBB']
    observed_forms = []
    with zvbb_trace.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if int(row['pc'], 16) < 0x80000000:
                continue
            word = int(row['instruction'], 16)
            observed_forms.extend((entry['name'], bool(word & (1 << 25))) for entry in encodings
                                  if word & entry['mask'] == entry['match'])
    assert observed_forms == [(case['form'], case['mode'] != 'masked_restart') for case in zvbb_cases]
    assert zvbb_native.MARKER in (ROOT / zvbb['run']['log']).read_text(encoding='utf-8')

    top = 'rv23_instruction_fetch_atomic_tb'
    fetch_log = audit_testbench(f'out/regression/{top}/report.json', 'run_instruction_fetch_atomicity.py', top, rtl)
    fetch_rows = [tuple(map(int, row)) for row in re.findall(
        r'^IFETCH_ATOMIC offset=(\d+) old=(\d+) new=(\d+) refill_overlaps=(\d+)$', fetch_log, re.MULTILINE)]
    fetch_witness = re.search(rf'^PASS {top} offsets=(\d+) refill_overlaps=(\d+)$', fetch_log, re.MULTILINE)
    assert [offset for offset, *_ in fetch_rows] == list(range(0, 64, 4))
    assert all(old > 0 and new > 0 and overlaps > 0 for _, old, new, overlaps in fetch_rows)
    fetch_overlaps = sum(row[3] for row in fetch_rows)
    assert fetch_witness and tuple(map(int, fetch_witness.groups())) == (len(fetch_rows), fetch_overlaps)
    mmu_log = audit_testbench('out/rva23/mmu.json', 'run_mmu_checks.py', 'rv23_mmu_tb',
                              ['rtl/soc/rv23_page_walker.sv', 'rtl/soc/rv23_mmu.sv'])
    mmu_witness = re.search(r'^PASS rv23_mmu_tb checks=(\d+) Sv39/Svade/PBMT/NAPOT/Sv39x4/implicit-PTE/faults$',
                            mmu_log, re.MULTILINE)
    assert mmu_witness and int(mmu_witness[1]) >= 103
    dump(ROOT / 'out/rva23/contract_evidence.json', dict(passed=True,
        complete_profile_validation=False,
        scope='Directed counter, LR/SC, WRS, pointer mask, CBO, CSR, fetch fault and RVV overlap and restart checks',
        audit_sha256=sha(__file__), source_inputs=inputs, reports=results,
        counter_cases=counter_cases, hpm_mode_filters=hpm['modes'], machine_overflow_interrupts=len(overflow['traps']),
        lrsc_placements=72, lrsc_successful_updates=1152, guest_wrs_contexts=len(wrs['cases']), external_wrs_wakes=wake['outcomes'].count('WRS.NTO'),
        external_lrsc_outcomes=wake['interference'],
        masked_guest_faults=4, vu_vector_retries=len(vu_retries), cbo_permission_outcomes=cbo['outcomes'],
        interrupt_csr_boundaries=interrupt['outcomes'], rv64_platform_interrupts=platform['traps'],
        guest_timer_wrap=timer_outcomes,
        guest_stateen=stateen_outcomes,
        guest_interrupt_priority=priority_outcomes,
        sv39x4_root_probes=root['probes'], sv39x4_hinval_remaps=root['remaps'], vs_hinval_remap=root['vs_remap'],
        csr_geometry_cases=geometry['case_count'],split_fetch_cases=12,split_fetch_traps=24,
        vector_overlap_restart=outcomes,
        guest_superpage_reads=len(superpage_results['loads']), guest_superpage_stores=superpage_results['stores'],
        guest_superpage_traps=len(superpage_results['traps']),
        hlv_hlvx_permission_cases=len(permission_cases), hlv_hlvx_traps=len(expected_traps),
        zvbb_native=zvbb_outcomes,
        instruction_fetch_offsets=len(fetch_rows), instruction_fetch_refill_overlaps=fetch_overlaps,
        mmu_checks=int(mmu_witness[1])))
    print('PASS current contract evidence: 960 counter cases, 5 HPM mode filters, 2 machine overflow IRQs, 72 LR/SC placements, 6 guest WRS contexts, 4 external WRS wakes, 4 masked guest faults, 255 CBO permissions, 8 immediate interrupt boundaries, RV64 platform, Sv39x4 root and boundary, 279 CSR cases, 12 split-fetch cases; full normative audit remains open')


if __name__ == '__main__':
    main()

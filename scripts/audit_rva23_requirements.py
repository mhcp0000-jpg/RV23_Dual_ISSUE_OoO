"""Check required-name/path traceability; never infer architectural compliance."""
import argparse
import csv
import json
import re
import subprocess
import sys

import run_guest_pbmt_precedence as guest_pbmt
import run_hypervisor_sie_isolation as sie_isolation
import run_profile_csr_geometry as csr_geometry
from sim_runner import GCC, ROOT, dump, sha, source_inputs

def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))


def timing_instruction_coverage(scalar_elf, scalar_schedule, vector_rows):
    # Zkt scalar listing intersected with the RV64 instructions in this core.
    # RV64 zext.h is the supported packw encoding with rs2=x0.
    scalar_required = set('''lui auipc addi slti sltiu xori ori andi slli srli srai
        add sub sll slt sltu xor srl sra or and addiw slliw srliw sraiw addw subw sllw srlw sraw
        mul mulh mulhsu mulhu mulw c.nop c.addi c.addiw c.lui c.srli c.srai c.andi c.sub
        c.xor c.or c.and c.subw c.addw c.slli c.mv c.add ror rol rori rorw rolw roriw
        andn orn xnor zext.h rev8 czero.eqz czero.nez'''.split())
    disassembly = subprocess.check_output(
        [str(GCC / 'riscv-none-elf-objdump.exe'), '-d', '-M', 'no-aliases,numeric', scalar_elf],
        cwd=ROOT, text=True, timeout=30)
    decoded = {int(pc, 16): (int(word, 16), name) for pc, word, name in
               re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(\S+)', disassembly, re.M)}
    scalar_measured = set()
    for pc, word, _ in scalar_schedule:
        encoding, mnemonic = decoded[int(pc, 16)]
        assert int(word, 16) & (0xffff if encoding & 3 != 3 else 0xffffffff) == encoding
        scalar_measured.add('c.nop' if encoding == 1 else mnemonic)
    assert scalar_required <= scalar_measured, sorted(scalar_required - scalar_measured)

    # Instruction families listed by Zvkt. Explicit forms distinguish the
    # required vector moves from vmv.x.s and Zvbb vcpop.v from vcpop.m.
    vector_stems = set('''vadd vsub vrsub vwaddu vwadd vwsubu vwsub vadc vmadc vsbc vmsbc
        vmseq vmsne vmslt vmsltu vmsle vmsleu vmsgt vmsgtu vmv1r vmv2r vmv4r vmv8r
        vsext vzext vand vmand vmandn vmor vmorn vmnand vmnor vmxor vmxnor vor vxor
        vmul vmulh vmulhu vmulhsu vwmul vwmulu vwmulsu vmacc vmadd vnmsac vnmsub
        vwmacc vwmaccu vwmaccsu vwmaccus vmerge vrgather vrgatherei16 vnsra vnsrl
        vsll vsra vsrl vslide1up vslide1down vfslide1up vfslide1down vslideup vslidedown'''.split())
    vector_moves = {'vmv.s.x', 'vmv.v.i', 'vmv.v.v', 'vmv.v.x'}
    table = read('config/vector_opcode_tables/encodings.json')['instructions']
    required_modes = {(entry['name'], vm) for entry in table
                      if entry['extension'] == 'ZVBB' or entry['name'].split('.')[0] in vector_stems
                      or entry['name'] in vector_moves
                      for vm in (0, 1) if not entry['mask'] & (1 << 25) or vm == (entry['match'] >> 25) & 1}
    legal_words = {(int(row['group']), int(row['instruction'], 16)) for row in vector_rows
                   if row['illegal'] == '0'}
    measured_modes = set()
    for group, word in legal_words:
        entry = table[group - 1]
        assert word & entry['mask'] == entry['match'], (group, word)
        measured_modes.add((entry['name'], (word >> 25) & 1))
    assert required_modes <= measured_modes, sorted(required_modes - measured_modes)
    return dict(scalar_mnemonics=sorted(scalar_required),
                vector_mnemonics=sorted({name for name, _ in required_modes}),
                vector_mask_encoding_pairs=len(required_modes),
                opcode_table_sha256=sha(ROOT / 'config/vector_opcode_tables/encodings.json'))


def recheck_timing():
    scalar = read('out/rva23/scalar_timing/report.json')
    baseline = None
    entry_cycles = []
    varied_results = {}
    for case in scalar['runs']:
        symbols = subprocess.check_output(
            [str(GCC / 'riscv-none-elf-nm.exe'), '-n', case['elf']],
            cwd=ROOT, text=True, timeout=30)
        labels = {}
        for line in symbols.splitlines():
            fields = line.split()
            if len(fields) == 3 and fields[2] in {'timing_start', 'timing_end'}:
                labels[fields[2]] = int(fields[0], 16)
        with (ROOT / case['trace']).open(newline='') as stream:
            rows = [row for row in csv.DictReader(stream)
                    if labels['timing_start'] - 4 <= int(row['pc'], 16) < labels['timing_end']]
        anchor = rows.pop(0)
        assert int(anchor['pc'], 16) == labels['timing_start'] - 4 and anchor['trap'] == '0'
        assert len(rows) == scalar['measured_instructions'], case['trace']
        assert all(row['trap'] == '0' for row in rows), case['trace']
        first_cycle = int(rows[0]['cycle'])
        entry_cycles.append(first_cycle - int(anchor['cycle']))
        schedule = [(row['pc'], row['instruction'], int(row['cycle']) - first_cycle)
                    for row in rows]
        if baseline is None:
            baseline = schedule
        assert schedule == baseline, case['trace']
        for row in rows:
            varied_results.setdefault(row['pc'], set()).add(row['wdata'])
    assert baseline[-1][2] + 1 == scalar['cycles']
    assert len(set(entry_cycles)) == 1 and entry_cycles[0] >= 0
    assert sum(len(values) > 1 for values in varied_results.values()) == scalar['instructions_with_varied_results']

    folder = ROOT / 'out/rva23/vector_timing'
    vector = read('out/rva23/vector_timing/report.json')
    with (folder / 'vectors.hex').open() as stream:
        packets = [tuple(int(field, 16) for field in line.split()) for line in stream]
    assert len(packets) == vector['packets']
    requests = [(group, instruction) for group, instruction, *_ in packets if group]
    with (folder / 'latencies.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    observed = [(int(row['group']), int(row['instruction'], 16)) for row in rows]
    assert observed == requests
    assert len(set(observed)) == vector['encoding_variants']
    assert all(int(row['cycles']) > 0 and row['illegal'] in {'0', '1'} for row in rows)
    return {
        'scalar_retirement_records': scalar['fixtures'] * len(baseline),
        'scalar_entry_cycles_after_anchor_retirement': entry_cycles[0],
        'scalar_pcs_with_different_results': scalar['instructions_with_varied_results'],
        'vector_request_records': len(observed),
        'vector_encoding_variants': len(set(observed)),
        'instruction_coverage': timing_instruction_coverage(scalar['runs'][0]['elf'], baseline, rows),
    }


def verify_probe_traps(trace):
    with trace.open(newline='', encoding='utf-8') as stream:
        rows = csv.reader(stream)
        header = next(rows)
        pc, instruction, trap, cause, tval = (header.index(name) for name in
                                             ('pc', 'instruction', 'trap', 'cause', 'tval'))
        traps = [(int(row[cause]), int(row[instruction], 16), int(row[tval], 16))
                 for row in rows if row[trap] == '1' and 0x80080000 <= int(row[pc], 16) < 0x80090000]
    assert traps == [(9, 0x73, 0), (9, 0x73, 0), (5, 0, 0)], traps


def recheck_opensbi_handoff():
    path = 'out/opensbi_handoff_htif/report.json'
    record = read(path)
    base_path = 'out/act4/dut/model.json'
    base = read(base_path)
    model = record['boot_model']
    run = record['run']
    assert record['passed'] and model['passed'] and run['passed'] and run['exit_code'] == 0
    assert record['model_sha256'] == sha(ROOT / base_path)
    assert model['top'] == base['top'] and model['params'] == base['params']
    assert '-GXLEN=64' in model['params'] and '-GHAS_SMODE=1' in model['params']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    assert sha(ROOT / record['elf']) == record['elf_sha256']
    rtl = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines()
    assert all(model['inputs'].get(name) == digest for name, digest in source_inputs(rtl).items())
    for inputs in (model['inputs'], record['inputs']):
        for name, digest in inputs.items():
            assert sha(ROOT / name) == digest, name

    log = ROOT / run['log']
    assert sha(log) == run['log_sha256']
    output = log.read_text(encoding='utf-8', errors='replace')
    markers = ('OPENSBI S-MODE DTB AND TIMER PASS', '[host-finish code=0]', 'PASS rv_act4_program_tb')
    positions = [output.find(marker) for marker in markers]
    assert all(position >= 0 for position in positions) and positions == sorted(positions), log
    trace = 'out/opensbi_handoff_htif/retire.csv'
    verify_probe_traps(ROOT / trace)
    return {path: sha(ROOT / path), trace: sha(ROOT / trace)}


def recheck_integration(linux_variant, require_linux_supm):
    linux_options = ['--variant', linux_variant, '--require-isa']
    if require_linux_supm:
        linux_options.append('--require-supm')
    audits = [
        ('audit_act4_results.py', ['--current'], 'out/act4/current_execution_audit.json'),
        ('run_act4_upstream_h.py', ['--check'], 'out/act4/upstream_h_extended/audit.json'),
        ('run_act4_current_h.py', ['--extended', '--check'], 'out/act4/current_h_extended/audit.json'),
        ('audit_act4_current_rva23.py', [], 'out/act4/current_rva23_inventory/execution_audit.json'),
        ('run_guest_misaligned.py', ['--check'], 'out/rva23/guest_misaligned/report.json'),
        ('run_guest_pte_mxr.py', ['--check'], 'out/rva23/guest_pte_mxr/report.json'),
        ('audit_rv32_release.py', [], 'out/rv32_release_audit.json'),
        ('audit_linux_boot.py', linux_options,
         f'out/linux_bringup/{linux_variant}/boot_audit.json'),
        ('audit_rv64_ooo_integration.py', [], 'out/rva23/rv64_ooo/audit.json'),
        ('audit_profile_contracts.py', [], 'out/rva23/contract_evidence.json'),
        ('run_fence_order.py', ['--check'], 'out/rva23/fence_order/report.json'),
        ('audit_ptw_debug_coherence.py', ['--with-negative'], 'out/rva23/ptw_debug_coherence/audit.json'),
        ('audit_sail_event_comparison.py', [], 'out/rva23/sail_privileged_events/audit.json'),
        ('audit_vector_agnostic_differential.py', [], 'out/rva23/vector_agnostic_differential/audit.json'),
        ('run_vector_fp_differential.py', ['--check'], 'out/rva23/vector_fp_differential/report.json'),
        ('run_vector_mixed_eew_sail.py', ['--check'], 'out/rva23/vector_mixed_eew_sail/report.json'),
        ('audit_timing_contract.py', [], 'out/rva23/timing_contract_evidence.json'),
    ]
    reports = {}
    for script, options, report in audits:
        subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *options], cwd=ROOT, check=True)
        result = read(report)
        if script == 'audit_act4_results.py':
            assert result['all_selected_passed'] and result['negative_control_passed'], report
        else:
            assert result['passed'] is True, report
        reports[report] = sha(ROOT / report)
    reports.update(recheck_opensbi_handoff())
    return reports


def recheck_sie_isolation():
    folder = sie_isolation.FOLDER
    current, before = (read(path.relative_to(ROOT) / 'report.json')
                       for path in (folder, folder / 'before'))
    model = current['model']
    prior_model = before['model']
    assert current['passed'] and before['passed'] and not current['before'] and before['before']
    assert current['generator_sha256'] == before['generator_sha256'] == sha(sie_isolation.__file__)
    assert current['runtime_inputs'] == before['runtime_inputs']
    assert sie_isolation.SOURCE in current['runtime_inputs']
    assert current['elf_sha256'] == before['elf_sha256'] == sha(folder / 'test.elf')
    assert current['compile'] == before['compile']
    sie_isolation.verify_model_pair(model, prior_model)
    assert all(option in model['params'] for option in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'))
    for name, digest in {**model['inputs'], **current['runtime_inputs']}.items():
        assert sha(ROOT / name) == digest, name
    for record, path, marker, code in ((current, folder, 'data=0x48534945', 0),
                                      (before, folder / 'before', 'data=0x42414449', 1)):
        trace = path / 'commit.csv'
        assert sha(trace) == record['trace_sha256']
        traps = sie_isolation.verify_trace(trace, record['before'])
        assert traps == record['traps']
        assert [int(trap['instruction'], 16) for trap in traps] == ([0] if code else [0, 0, 0x73])
        for phase in ('compile', 'run'):
            result = record[phase]
            assert result['passed'] and result['exit_code'] == 0
            assert sha(ROOT / result['log']) == result['log_sha256']
        output = (ROOT / record['run']['log']).read_text(encoding='utf-8')
        assert marker in output and f'[host-finish code={code}]' in output
    return {path.relative_to(ROOT).as_posix(): sha(path)
            for path in (folder / 'report.json', folder / 'before/report.json')}


def recheck_guest_pbmt():
    folder = ROOT / guest_pbmt.FOLDER
    control = ROOT / guest_pbmt.CONTROL
    path = folder / 'report.json'
    record = read(path)
    model = record['model']
    assert record['passed'] and record['generator_sha256'] == sha(ROOT / 'scripts/run_guest_pbmt_precedence.py')
    assert all(option in model['params'] for option in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1', '-GHAS_MMU=1'))
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    for name, digest in {**model['inputs'], **record['runtime_inputs']}.items():
        assert sha(ROOT / name) == digest, name
    for artifact, key in (('test.S', 'source'), ('test.elf', 'elf'), ('commit.csv', 'trace')):
        assert sha(folder / artifact) == record[key + '_sha256']
    assert (folder / 'test.S').read_text(encoding='utf-8') == guest_pbmt.fixture()
    assert record['outcomes'] == guest_pbmt.verify_trace(folder / 'commit.csv')

    before = record['pre_fix']
    previous = before['model']
    mmu = guest_pbmt.MMU_PATH
    previous_inputs = guest_pbmt.control_inputs(previous)
    assert previous['params'] == model['params'] and previous_inputs.keys() == model['inputs'].keys()
    assert {name for name in model['inputs'] if model['inputs'][name] != previous_inputs[name]} == {mmu}
    assert sha(control / 'rv23_mmu.sv') == previous_inputs[mmu]
    assert sha(ROOT / before['binary']) == previous['binary_sha256']
    old_trace = control / 'native_commit.csv'
    assert sha(old_trace) == before['trace_sha256']
    assert before['outcomes'] == guest_pbmt.verify_trace(old_trace, pre_fix=True)
    for run, witnesses in ((record['compile'], ()),
                           (record['run'], (guest_pbmt.MARKER, '[host-finish code=0]')),
                           (before['run'], ('data=0x00000006', '[host-finish code=1]'))):
        log = ROOT / run['log']
        assert run['passed'] and run['exit_code'] == 0 and sha(log) == run['log_sha256']
        output = log.read_text(encoding='utf-8', errors='replace')
        assert all(witness in output for witness in witnesses), log
    return sha(path)


def recheck_hgatp_warl():
    folder = ROOT / 'out/rva23/hgatp_warl_comparison'
    path = folder / 'report.json'
    report = read(path)
    model = report['model']
    assert report['passed'] and report['driver_sha256'] == sha(csr_geometry.__file__)
    assert model == read('out/rva23/hypervisor_integration/model.json')
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    for name, digest in {**model['inputs'], **report['runtime_inputs'], **report['artifacts']}.items():
        assert sha(ROOT / name) == digest, name

    elf_name, = (name for name in report['artifacts'] if name.endswith('/test.elf'))
    archive = (ROOT / elf_name).parent
    assert report['artifacts'][elf_name] == report['elf_sha256']
    before = read(archive / 'model.json')
    hcsr = 'rtl/backend/rv_hypervisor_csrs.sv'
    assert before['params'] == model['params'] and before['inputs'].keys() == model['inputs'].keys()
    assert {name for name, digest in model['inputs'].items() if before['inputs'][name] != digest} == {hcsr}
    assert sha(archive / 'before.sv') == before['inputs'][hcsr]
    assert sha(archive / 'before.exe') == before['binary_sha256']
    code, cases, _ = csr_geometry.fixture()
    assert (archive / 'test.S').read_text(encoding='utf-8') == code and read(archive / 'cases.json') == cases
    hgatp = [case for case in cases if case['csr'] == 'hgatp']
    assert report['rejected_before_case'] == hgatp[1]['id'] == 218

    for phase, code, markers in (
            ('before', 1, ('data=0x000000da', 'ELF reported failure exit code 1')),
            ('after', 0, ('data=0x43535247', 'PASS rv32_program_tb'))):
        run = report[phase]
        log = ROOT / run['log']
        assert run['passed'] and run['exit_code'] == code and sha(log) == run['log_sha256']
        output = log.read_text(encoding='utf-8')
        assert re.findall(r'opening ELF: (\S+)', output) == [elf_name]
        assert all(marker in output for marker in markers)

    for trace, expected in (('replay-before.csv', hgatp[:2]), ('commit.csv', hgatp)):
        trace_path = folder / trace
        assert trace_path.relative_to(ROOT).as_posix() in report['artifacts']
        with trace_path.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        accesses = [row for row in rows if row['csr_valid'] == '1' and row['csr_addr'] == '680']
        assert [int(row['csr_wdata'], 16) for row in accesses if row['csr_we'] == '1'] == [
            case['value'] for case in expected]
        reads = [int(row['wdata'], 16) for row in accesses if row['rd_write'] == '1']
        if trace == 'replay-before.csv':
            assert reads == [expected[0]['expected']] * 2 and reads[-1] != expected[1]['expected']
        else:
            assert reads == [case['expected'] for case in expected]
            assert csr_geometry.direct_vector_trace(rows) == report['direct_entries']
    return sha(path)


def requirement_execution(required, evidence, evidence_map, entries):
    known_reports = dict(evidence['integration_report_hashes'])
    for key, path in {
        'same_elf_hypervisor_replay_sha256': 'out/rva23/profile_hypervisor_replay/report.json',
        'sail_reference_evidence_sha256': 'out/rva23/sail_reference_evidence.json',
        'mprv_guest_fault_metadata_sha256': 'out/rva23/hypervisor_mprv_faults/report.json',
        'guest_pbmt_precedence_sha256': 'out/rva23/guest_pbmt_precedence/report.json',
        'hgatp_warl_comparison_sha256': 'out/rva23/hgatp_warl_comparison/report.json',
    }.items():
        known_reports[path] = evidence[key]
    known_reports.update(evidence['hs_sie_isolation_report_hashes'])
    contract = read('out/rva23/contract_evidence.json')
    known_reports.update({path if path.endswith('.json') else f'{path}/report.json': digest
                          for path, digest in contract['reports'].items()})
    hypervisor = 'out/rva23/hypervisor_checkpoint.json'
    assert sha(ROOT / hypervisor) == evidence['hypervisor_checkpoint_sha256']
    hypervisor_audit = read(hypervisor)
    assert hypervisor_audit['audit_sha256'] == sha(ROOT / 'scripts/audit_hypervisor_integration.py')
    breakpoint = next(entry for entry in hypervisor_audit['evidence']
                      if entry.get('case') == 'hypervisor_breakpoint_metadata')
    known_reports['out/rva23/hypervisor_breakpoint_metadata/report.json'] = breakpoint['report_sha256']
    act = read('out/act4/current_execution_audit.json')
    act_requirements = act['passed_checked_in_exact_requirements']
    vector_suites = act['passed_generated_vector_suites']
    rows = {name: dict(act4_literal_requirement_passes=act_requirements.get(name, 0),
                       directed_evidence=[]) for name in sorted(required | {'I'})}
    # These tags are the instruction subsets exercised by the selected tests.
    # Each count is per tag and a single test can have several tags.
    for name, tags in {'A': ['Zaamo', 'Zalrsc'], 'B': ['Zba', 'Zbb', 'Zbs'],
                       'C': ['Zca', 'Zcd'], 'Ss1p13': ['S']}.items():
        rows[name]['act4_related_tag_passes'] = {tag: act_requirements[tag] for tag in tags}
    rows['V']['act4_generated_suite_passes'] = {name: count for name, count in vector_suites.items()
                                              if name.startswith(('Vx', 'Vls', 'Vf'))}
    rows['Zvfhmin']['act4_generated_suite_passes'] = {'Zvfhmin': vector_suites['Zvfhmin']}
    for entry in entries:
        report = entry['report']
        if not report.endswith('.json'):
            report += '/report.json'
        digest = known_reports[report]
        assert sha(ROOT / report) == digest, report
        for name in entry['requirements']:
            rows[name]['directed_evidence'].append(dict(report=report, sha256=digest, behavior=entry['behavior']))
    return dict(mapping_sha256=sha(ROOT / evidence_map), requirements=rows,
                without_mapped_execution=[name for name, row in rows.items()
                                          if not any(row.values())])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--with-evidence',action='store_true',help='Also require the current full implemented-feature checkpoint')
    parser.add_argument('--with-integration-evidence', action='store_true',
                        help='Recheck current execution artifacts in addition to the feature checkpoint')
    parser.add_argument('--linux-variant', default='modern_isa',
                        help='Name of the completed current-source Linux run used by the integration audit')
    parser.add_argument('--require-linux-supm', action='store_true',
                        help='Require the selected integration Linux run to verify userspace pointer masking')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', args.linux_variant):
        parser.error('invalid Linux variant name')
    if args.require_linux_supm and not args.with_integration_evidence:
        parser.error('--require-linux-supm requires --with-integration-evidence')
    require_checkpoint = args.with_evidence or args.with_integration_evidence

    inventory=read('config/rva23_required_extensions.json')
    mapping=read('config/rva23_implementation_map.json')
    keys=['mandatory_unprivileged_inherited_from_RVA23U64','mandatory_unprivileged_added_by_RVA23S64','mandatory_supervisor','Sha_components']
    required=set().union(*(set(inventory[key]) for key in keys))
    evidence_map = 'config/rva23_execution_evidence.json'
    execution_entries = read(evidence_map)
    for entry in execution_entries:
        assert set(entry['requirements']) <= required | {'I'} and entry['behavior'], entry
    mapped=[name for group in mapping['groups'] for name in group['requirements']]
    assert len(mapped)==len(set(mapped))==58 and set(mapped)==required
    assert not mapping['complete_profile_validation']
    assert mapping['base']['isa']=='RV64I' and mapping['base']['endianness']=='little'
    rtl=(ROOT/'rtl/filelist.f').read_text(encoding='utf-8').splitlines()
    assert rtl==(ROOT/'sim/sources.f').read_text(encoding='utf-8').splitlines()
    inputs=source_inputs(rtl)
    drivers=set(mapping['base']['checks']+mapping.get('integration_checks',[]));paths=set(mapping['base']['rtl']+mapping['integration'])
    for group in mapping['groups']:
        assert group['contract'] and group['status']
        drivers.update(group['checks']);paths.update(group['rtl'])
    assert paths<=set(inputs),paths-set(inputs)
    for driver in drivers:assert (ROOT/'scripts'/driver).is_file(),driver
    evidence={}
    if require_checkpoint:
        checkpoint=read('out/rva23/functional_checkpoint.json')
        assert checkpoint['passed'] and checkpoint['source_sha256']==inputs
        assert len(checkpoint['steps'])==70
        for step in checkpoint['steps']:
            assert step['passed'] and sha(ROOT/'scripts'/step['script'])==step['sha256']
        evidence['functional_checkpoint_sha256']=sha(ROOT/'out/rva23/functional_checkpoint.json')
        for name in ['hypervisor_checkpoint','vector_architectural_evidence','timing_contract_evidence','upstream_isa_evidence']:
            path='out/rva23/'+name+'.json';record=read(path);assert record['passed']
            evidence[name+'_sha256']=sha(ROOT/path)
        path='out/rva23/upstream_privileged_evidence.json';privileged=read(path)
        assert privileged['passed'] and len(privileged['cases'])==16
        assert privileged['generator_sha256']==sha(ROOT/'scripts/run_upstream_privileged_tests.py')
        for entry in privileged['cases']:
            case_path='out/rva23/upstream_riscv_tests/'+entry['name']+'/report.json'
            assert sha(ROOT/case_path)==entry['report_sha256']
            case=read(case_path);assert case['passed'] and case['inputs']==entry['inputs']
            assert case['binary_sha256']==entry['binary_sha256']
            for p,h in case['inputs'].items():assert sha(ROOT/p)==h,p
            for artifact in ['elf','trace']:assert sha(ROOT/case[artifact])==case[artifact+'_sha256']
            for phase in ['compile','run']:
                r=case[phase];assert r['passed'] and r['exit_code']==0
                assert sha(ROOT/r['log'])==r['log_sha256']
        evidence['upstream_privileged_evidence_sha256']=sha(ROOT/path)
        path='out/rva23/profile_hypervisor_replay/report.json';replay=read(path)
        assert replay['passed'] and len(replay['cases'])==25
        native_inputs=source_inputs(rtl+['tb/e2e/dpi/rv_host_dpi.sv','tb/e2e/dpi/rv_commit_trace_logger.sv',
                                        'tb/rv32_program_tb.sv','tb/e2e/dpi/elf_loader.cpp'])
        assert replay['model']['inputs']==native_inputs and '-GHAS_H=1' in replay['model']['params']
        assert replay['model']['binary_sha256']==read('out/rva23/hypervisor_checkpoint.json')['binary_sha256']
        assert sha(ROOT/replay['model']['binary'])==replay['model']['binary_sha256']
        assert replay['generator_sha256']==sha(ROOT/'scripts/run_profile_hypervisor_replay.py')
        for case in replay['cases']:
            assert case['passed']
            for artifact in ['original_report','elf','baseline_trace','baseline_log','trace']:
                assert sha(ROOT/case[artifact])==case[artifact+'_sha256'],case[artifact]
            r=case['run'];assert r['passed'] and r['exit_code']==0
            assert sha(ROOT/r['log'])==r['log_sha256']
        evidence['same_elf_hypervisor_replay_sha256']=sha(ROOT/path)
        path='out/rva23/hypervisor_mprv_faults/report.json';mprv=read(path)
        assert mprv['passed'] and mprv['case_count']==10
        assert mprv['model']['inputs']==native_inputs and mprv['model']['binary_sha256']==replay['model']['binary_sha256']
        assert mprv['generator_sha256']==sha(ROOT/'scripts/run_hypervisor_mprv_faults.py')
        for filename,key in [('test.S','source'),('cases.json','cases'),('test.elf','elf'),('commit.csv','trace')]:
            assert sha(ROOT/'out/rva23/hypervisor_mprv_faults'/filename)==mprv[key+'_sha256']
        for phase in ['compile','run']:
            r=mprv[phase];assert r['passed'] and r['exit_code']==0
            assert sha(ROOT/r['log'])==r['log_sha256']
        evidence['mprv_guest_fault_metadata_sha256']=sha(ROOT/path)
        subprocess.run([sys.executable,str(ROOT/'scripts/audit_sail_comparison.py')],cwd=ROOT,check=True)
        path='out/rva23/sail_reference_evidence.json';sail=read(path)
        assert sail['passed'] and sail['upstream_elfs']==168 and sail['exact_user_elfs']==152
        assert sail['rtl_inputs']==native_inputs and sail['rtl_binary_sha256']==replay['model']['binary_sha256']
        assert sail['generator_sha256']==sha(ROOT/'scripts/audit_sail_comparison.py')
        evidence['sail_reference_evidence_sha256']=sha(ROOT/path)
    if args.with_integration_evidence:
        evidence['hgatp_warl_comparison_sha256'] = recheck_hgatp_warl()
        evidence['guest_pbmt_precedence_sha256'] = recheck_guest_pbmt()
        evidence['hs_sie_isolation_report_hashes'] = recheck_sie_isolation()
        evidence['integration_report_hashes'] = recheck_integration(
            args.linux_variant, args.require_linux_supm)
        evidence['timing_artifact_comparison'] = recheck_timing()
        execution = requirement_execution(required, evidence, evidence_map, execution_entries)
        assert not execution['without_mapped_execution'], execution['without_mapped_execution']
        evidence['requirement_execution'] = execution
    dump(ROOT/'out/rva23/requirement_traceability.json',dict(passed=True,
        scope='58 mandatory names mapped to compiled RTL and executable check drivers; full normative/architectural compliance is not established',
        complete_profile_validation=False,required_count=58,implementation_groups=len(mapping['groups']),
        inventory_sha256=sha(ROOT/'config/rva23_required_extensions.json'),mapping_sha256=sha(ROOT/'config/rva23_implementation_map.json'),
        audit_sha256=sha(__file__),source_inputs=inputs,driver_inputs={name:sha(ROOT/'scripts'/name) for name in sorted(drivers)},
        current_checkpoint_required=require_checkpoint,evidence=evidence))
    print('PASS traceability: 58 required names, compiled integration paths and check drivers; architectural completion remains open',flush=True)


if __name__ == '__main__':
    main()

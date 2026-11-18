"""Validate completed RV64 CoreMark runs and publish compact measured evidence."""
import collections
import argparse
import hashlib
import csv
import json
import re
import subprocess

from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/performance/rv64_coremark'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--short-comparison', action='store_true', help='Publish the completed three-build 2-iteration stage; keep extended plan incomplete')
    mode.add_argument('--completed-runs', action='store_true', help='Publish completed runs including at least one extended run; keep plan incomplete')
    args = parser.parse_args()
    partial = args.short_comparison or args.completed_runs
    path = FOLDER / 'report.json'
    report_bytes = path.read_bytes()
    raw = json.loads(report_bytes)
    assert (raw['passed'] or partial) and not raw['certified_score']
    assert raw['driver_sha256'] == sha(ROOT / 'scripts/run_coremark_rv64.py')
    assert raw['compiler_sha256'] == sha(GCC / 'riscv-none-elf-gcc.exe')
    assert source_inputs(raw['inputs']) == raw['inputs']
    model = raw['model']
    assert source_inputs(model['inputs']) == model['inputs']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    expected = {(variant, count) for variant in ('o2_scalar', 'o3_scalar', 'o3_rvv')
                for count in ((2,) if args.short_comparison else (2, 10))}
    if args.completed_runs:
        completed = {(case['variant'], case['iterations']) for case in raw['cases']}
        assert completed <= expected and any(count == 10 for _, count in completed)
        expected = completed
    selected = [case for case in raw['cases'] if (case['variant'], case['iterations']) in expected]
    assert {(case['variant'], case['iterations']) for case in selected} == expected
    assert len(selected) == len(expected)
    rows, artifacts, crcs = [], {}, {}
    for case in selected:
        folder = FOLDER / f"{case['variant']}_{case['iterations']}"
        elf = folder / 'coremark.elf'
        assert sha(elf) == case['elf_sha256']
        for step in ('compile', 'run'):
            run = case[step]
            assert run['passed'] and run['exit_code'] == 0
            assert sha(ROOT / run['log']) == run['log_sha256']
            artifacts[run['log']] = run['log_sha256']
        log = (ROOT / case['run']['log']).read_text(encoding='utf-8')
        assert 'PASS rv32_program_tb' in log
        values = [int(value, 16) for value in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]', log)]
        start = values.index(0x434d0001)
        packet = values[start:start + 12]
        assert packet == case['packet'] and packet[11] & 0x17 == 1
        assert packet[6:10] == [0xe9f5, 0xe714, 0x1fd7, 0x8e3a]
        cycles, instructions = packet[2] + (packet[3] << 32), packet[4] + (packet[5] << 32)
        assert cycles == case['cycles'] and instructions == case['instructions']
        assert case['ipc'] == instructions / cycles
        assert case['coremark_per_mhz_estimate'] == case['iterations'] * 1000000 / cycles
        crc = packet[6:11]
        assert crcs.setdefault(case['iterations'], crc) == crc
        disassembly = folder / 'disassembly.txt'
        text = disassembly.read_text(encoding='utf-8')
        decoded = {int(pc, 16): mnemonic for pc, mnemonic in
                   re.findall(r'^\s*([\da-f]+):\s+[\da-f]+\s+(\S+)', text, re.M)}
        vector = [name for name in decoded.values() if name.startswith('v')]
        assert len(vector) == case['static_vector_instructions']
        artifacts[disassembly.relative_to(ROOT).as_posix()] = sha(disassembly)
        row = {key: case[key] for key in ('variant', 'iterations', 'cycles', 'instructions', 'ipc',
            'coremark_per_mhz_estimate', 'elf_sha256', 'flags', 'packet', 'static_vector_instructions', 'whole_program_counters')}
        row['execution_driver_sha256'] = case['driver_sha256']
        row['flags'] = [flag.replace(str(ROOT), '.') for flag in row['flags']]
        if 'profile' in case:
            trace = folder / 'commit.csv'
            assert sha(trace) == case['trace_sha256']
            artifacts[trace.relative_to(ROOT).as_posix()] = sha(trace)
            profile = case['profile'].copy()
            # The legacy logger calls some implemented Zb operations ILLEGAL.
            # Use objdump's decoded mnemonic for this diagnostic histogram;
            # hardware trap bits were checked separately by the run driver.
            mix = collections.Counter()
            gap_cycles, gap_events, vector_kinds = collections.Counter(), collections.Counter(), collections.Counter()
            previous_cycle = None
            active, stopped = False, False
            start_symbol = re.search(r'^([\da-f]+) <start_time>:', text, re.M)
            stop_symbol = re.search(r'^([\da-f]+) <stop_time>:', text, re.M)
            assert start_symbol and stop_symbol
            start_pc, stop_pc = int(start_symbol[1], 16), int(stop_symbol[1], 16)
            with trace.open(newline='') as stream:
                for item in csv.DictReader(stream):
                    pc = int(item['pc'], 16)
                    if not active:
                        active = pc == start_pc
                    if not active:
                        continue
                    if pc == stop_pc:
                        stopped = True
                        break
                    assert item['trap'] == '0'
                    mix[decoded[pc]] += 1
                    cycle, word = int(item['cycle']), int(item['instruction'], 16)
                    if previous_cycle is not None and cycle > previous_cycle + 1:
                        gap_cycles[pc] += cycle - previous_cycle - 1
                        gap_events[pc] += 1
                    previous_cycle = cycle
                    opcode, funct3 = word & 127, (word >> 12) & 7
                    if opcode == 0x57:
                        vector_kinds['configuration' if funct3 == 7 else 'arithmetic'] += 1
                    elif opcode in (7, 0x27) and funct3 in (0, 5, 6, 7):
                        vector_kinds['loads' if opcode == 7 else 'stores'] += 1
            assert stopped and sum(mix.values()) == profile['retirements']
            profile['instruction_mix'] = mix.most_common(16)
            profile['scalar_div_rem_instructions'] = sum(count for name, count in mix.items()
                if name in ('div', 'divu', 'divw', 'divuw', 'rem', 'remu', 'remw', 'remuw'))
            profile['vector_div_rem_instructions'] = sum(count for name, count in mix.items()
                if name.startswith(('vdiv', 'vrem')))
            assert sum(vector_kinds.values()) == profile['vector_instructions']
            profile['vector_breakdown'] = dict(vector_kinds)
            profile['largest_gap_pcs'] = [dict(pc=f'{pc:016x}', mnemonic=decoded[pc],
                gap_cycles=count, events=gap_events[pc]) for pc, count in gap_cycles.most_common(10)]
            row['profile'] = profile
        rows.append(row)
    probe_path = ROOT / 'out/performance/rv64_latency/report.json'
    probe = json.loads(probe_path.read_bytes())
    assert probe['passed'] and probe['driver_sha256'] == sha(ROOT / 'scripts/profile_rv64_latency.py')
    assert probe['model'] == model and source_inputs(probe['inputs']) == probe['inputs']
    assert sha(ROOT / 'out/performance/rv64_latency/test.elf') == probe['elf_sha256']
    repeated = probe['repeat']
    assert repeated['passed'] and repeated['elf_sha256'] == probe['elf_sha256']
    again = repeated['run']
    assert again['passed'] and again['exit_code'] == 0 and sha(ROOT / again['log']) == again['log_sha256']
    artifacts[again['log']] = again['log_sha256']
    for key in ('compile', 'run'):
        record = probe[key]
        assert record['passed'] and record['exit_code'] == 0 and sha(ROOT / record['log']) == record['log_sha256']
        artifacts[record['log']] = record['log_sha256']
    artifacts[probe_path.relative_to(ROOT).as_posix()] = sha(probe_path)
    snapshot = FOLDER / ('report_short_snapshot.json' if args.short_comparison else
                         'report_progress_snapshot.json' if args.completed_runs else 'report_final_snapshot.json')
    snapshot.write_bytes(report_bytes)
    report_digest = hashlib.sha256(report_bytes).hexdigest()
    artifacts[snapshot.relative_to(ROOT).as_posix()] = report_digest
    compact = dict(passed=True, certified_score=False, complete_benchmark_plan=not partial,
        scope='Short, CRC-checked RTL performance estimates; no measured silicon clock or certified CoreMark result',
        source_report_sha256=report_digest, upstream_commit=raw['upstream_commit'],
        execution_driver_sha256=raw['driver_sha256'],
        resumed_driver_sha256=raw.get('resumed_driver_sha256'),
        model_binary_sha256=model['binary_sha256'], rtl_inputs=model['inputs'],
        software_inputs=raw['inputs'], compiler_sha256=raw['compiler_sha256'],
        compiler_version=subprocess.check_output([str(GCC / 'riscv-none-elf-gcc.exe'), '--version'], text=True).splitlines()[0],
        reporting_driver_sha256=sha(__file__), cases=rows, latency_probes=probe['cases'], artifacts=artifacts)
    target = ('coremark_rv64_short.json' if args.short_comparison else
              'coremark_rv64_progress.json' if args.completed_runs else 'coremark_rv64.json')
    dump(ROOT / 'docs/evidence' / target, compact)
    lines = ['| Build | Iterations | Cycles | Instructions | IPC | CoreMark/MHz estimate | Static V |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append(f"| {row['variant']} | {row['iterations']} | {row['cycles']:,} | {row['instructions']:,} | {row['ipc']:.6f} | {row['coremark_per_mhz_estimate']:.6f} | {row['static_vector_instructions']} |")
    (FOLDER / 'measured_table.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('PASS completed RV64 CoreMark stage:', len(rows), 'runs; CRC equality per iteration and current content hashes;',
          'extended benchmark plan complete:', not partial)


if __name__ == '__main__':
    main()

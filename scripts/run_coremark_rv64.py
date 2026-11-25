"""Compare unchanged CoreMark on RV64 scalar/RVV builds; short RTL estimates."""
import argparse
import bisect
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


BENCH = 'sw/benchmarks/coremark/'
FOLDER = ROOT / 'out/performance/rv64_coremark'
VARIANTS = {'o2_scalar': ['-O2', '-fno-tree-vectorize'],
            'o3_scalar': ['-O3', '-fno-tree-vectorize'],
            'o3_rvv': ['-O3', '-ftree-vectorize', '-fvect-cost-model=dynamic', '-mrvv-vector-bits=zvl']}


def analyze_trace(trace, elf):
    nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', elf.relative_to(ROOT).as_posix()], text=True)
    symbols = [(int(pc, 16), name) for pc, name in re.findall(r'^([\da-f]+) [tT] (\S+)$', nm, re.M)]
    symbol_pcs = [pc for pc, _ in symbols]
    start = next(pc for pc, name in symbols if name == 'start_time')
    stop = next(pc for pc, name in symbols if name == 'stop_time')
    active, previous_cycle = False, None
    groups = collections.Counter()
    gaps = collections.Counter()
    mix = collections.Counter()
    vector = 0
    with trace.open(newline='') as stream:
        for row in csv.DictReader(stream):
            pc, word, cycle = int(row['pc'], 16), int(row['instruction'], 16), int(row['cycle'])
            if pc == start:
                active = True
            if active and pc == stop:
                break
            if not active:
                continue
            assert row['trap'] == '0', row
            groups[cycle] += 1
            mix[row.get('mnemonic', f'{word & 127:02x}') ] += 1
            vector += word & 127 == 0x57 or (word & 127 in (7, 0x27) and (word >> 12) & 7 in (0, 5, 6, 7))
            if previous_cycle is not None and cycle > previous_cycle + 1:
                index = bisect.bisect_right(symbol_pcs, pc) - 1
                gaps[symbols[index][1]] += cycle - previous_cycle - 1
            previous_cycle = cycle
    assert groups and max(groups.values()) <= 2
    span = max(groups) - min(groups) + 1
    return dict(scope='start_time entry to stop_time entry; differs from CSR timed interval; gaps attributed to next retirement, not causal stalls',
        cycles=span, retirements=sum(groups.values()), no_retirement_cycles=span - len(groups),
        dual_retirement_cycles=sum(n == 2 for n in groups.values()), vector_instructions=vector,
        largest_gap_attribution=gaps.most_common(8), instruction_mix=mix.most_common(16))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, nargs='+', default=[2, 10])
    parser.add_argument('--variants', choices=VARIANTS, nargs='+', default=list(VARIANTS))
    parser.add_argument('--reuse-elf-report', type=Path,
                        help='Path to prior report.json; reuse its adjacent ELF after checking the hash')
    parser.add_argument('--no-trace', action='store_true', help='Skip the commit CSV for fixed ELF timing comparisons')
    parser.add_argument('--resume', action='store_true', help='Reuse only content-matching completed runs')
    args = parser.parse_args()
    assert all(n >= 2 for n in args.iterations)
    FOLDER.mkdir(parents=True, exist_ok=True)
    provenance = json.loads((ROOT / BENCH / 'upstream/PROVENANCE.json').read_bytes())
    for name, digest in provenance['files'].items():
        assert sha(ROOT / BENCH / 'upstream' / name) == digest
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_bytes())
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(model['params'])
    assert source_inputs(model['inputs']) == model['inputs'] and sha(ROOT / model['binary']) == model['binary_sha256']
    sources = [BENCH + 'rv64_start.S', BENCH + 'port64/core_portme.c'] + [
        BENCH + 'upstream/' + name for name in ('core_list_join.c', 'core_main.c', 'core_matrix.c', 'core_state.c', 'core_util.c')]
    inputs = source_inputs(sources + [BENCH + 'port64/core_portme.h', BENCH + 'upstream/coremark.h',
        BENCH + 'rv32_tim.ld', 'tb/fixtures/bootrom/bootrom_host_jump64.hex'])
    result = dict(passed=False, certified_score=False, model=model, inputs=inputs,
        driver_sha256=sha(__file__), compiler_sha256=sha(GCC / 'riscv-none-elf-gcc.exe'),
        upstream_commit=provenance['commit'], cases=[])
    report_path = FOLDER / 'report.json'
    previous = {}
    fixed = {}
    if args.reuse_elf_report:
        reference = args.reuse_elf_report.resolve()
        if reference == report_path.resolve():
            parser.error('The reference report must be outside the output folder')
        if args.resume:
            parser.error('--reuse-elf-report and --resume are separate run modes')
        for row in json.loads(reference.read_bytes())['cases']:
            fixed[row['variant'], row['iterations']] = row
    if args.resume and report_path.exists():
        old = json.loads(report_path.read_bytes())
        assert old['model'] == model and old['inputs'] == inputs
        assert old['compiler_sha256'] == result['compiler_sha256']
        result['resumed_report_sha256'] = sha(report_path)
        result['resumed_driver_sha256'] = old['driver_sha256']
        for row in old['cases']:
            row.setdefault('driver_sha256', old['driver_sha256'])
            previous[row['variant'], row['iterations']] = row
    with Simulator() as sim:
        for iterations in args.iterations:
            for variant in args.variants:
                options = VARIANTS[variant]
                folder = FOLDER / f'{variant}_{iterations}'
                folder.mkdir(parents=True, exist_ok=True)
                elf, disassembly = folder / 'coremark.elf', folder / 'disassembly.txt'
                flags = ['-march=rv64gcv_zba_zbb_zbs_zicond', '-mabi=lp64d', '-mcmodel=medany',
                    '-msmall-data-limit=0', '-ffreestanding', '-fno-builtin', '-fno-common',
                    '-fno-asynchronous-unwind-tables', '-fno-unwind-tables', '-nostdlib', '-nostartfiles',
                    '-fno-tree-loop-distribute-patterns', '-Wl,--build-id=none', '-Wl,--no-relax',
                    '-I' + BENCH + 'port64', '-I' + BENCH + 'upstream',
                    '-DPERFORMANCE_RUN=1', f'-DITERATIONS={iterations}', '-DTOTAL_DATA_SIZE=2000',
                    '-DMAIN_HAS_NOARGC=1', '-DMEM_METHOD=MEM_STATIC', '-DMULTITHREAD=1',
                    *options, '-fopt-info-vec-all=' + str(folder / 'vectorization.txt'),
                    '-T', BENCH + 'rv32_tim.ld', *sources]
                cached = previous.get((variant, iterations))
                if cached:
                    assert cached['flags'] == flags and sha(elf) == cached['elf_sha256']
                    for step in ('compile', 'run'):
                        record = cached[step]
                        assert record['passed'] and record['exit_code'] == 0
                        assert sha(ROOT / record['log']) == record['log_sha256']
                    if 'profile' in cached:
                        assert sha(folder / 'commit.csv') == cached['trace_sha256']
                    result['cases'].append(cached)
                    dump(report_path, result)
                    print('REUSED', variant, iterations, cached['cycles'], flush=True)
                    continue
                if args.reuse_elf_report:
                    reference_case = fixed[variant, iterations]
                    assert reference_case['run']['passed']
                    payload = (reference.parent / folder.name / 'coremark.elf').read_bytes()
                    assert hashlib.sha256(payload).hexdigest() == reference_case['elf_sha256']
                    elf.write_bytes(payload)
                    build = dict(reused_elf=True, reference_report_sha256=sha(reference))
                    flags = reference_case['flags']
                else:
                    build, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', *flags, '-o', elf], folder / 'compile.log', 120)
                digest = sha(elf)
                text = subprocess.check_output([str(GCC / 'riscv-none-elf-objdump.exe'), '-d', elf.relative_to(ROOT).as_posix()], text=True)
                disassembly.write_text(text, encoding='utf-8')
                static_vector = re.findall(r'^\s*[\da-f]+:\s+[\da-f]+\s+(v\S+)', text, re.M)
                trace = folder / 'commit.csv' if not args.no_trace and iterations == min(args.iterations) else None
                run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
                    *(['+trace_file=' + trace.relative_to(ROOT).as_posix()] if trace else []), '+quiet_commit',
                    f'+timeout_cycles={iterations * 10000000}', '+expected_exit_code=0'], folder / 'simulation.log', max(1800, iterations * 500))
                assert 'PASS rv32_program_tb' in log and 'ELF AXI readback PASS' in log
                values = [int(value, 16) for value in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]', log)]
                start = values.index(0x434d0001)
                packet = values[start:start + 12]
                assert len(packet) == 12 and packet[1] == iterations
                assert packet[6:10] == [0xe9f5, 0xe714, 0x1fd7, 0x8e3a] and packet[11] & 0x17 == 1, packet
                cycles, instructions = packet[2] + (packet[3] << 32), packet[4] + (packet[5] << 32)
                if args.reuse_elf_report:
                    assert instructions == reference_case['instructions']
                row = dict(variant=variant, iterations=iterations, driver_sha256=result['driver_sha256'], cycles=cycles, instructions=instructions,
                    ipc=instructions / cycles, coremark_per_mhz_estimate=iterations * 1000000 / cycles,
                    packet=packet, elf_sha256=digest, flags=flags, compile=build, run=run,
                    static_vector_instructions=len(static_vector), vector_mnemonics=sorted(set(static_vector)),
                    whole_program_counters={tag: {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', re.search(tag + r' (.*)', log)[1])}
                        for tag in ('CACHE_PERF', 'PATH_PERF')})
                if trace:
                    row.update(profile=analyze_trace(trace, elf), trace_sha256=sha(trace))
                assert sha(elf) == digest and source_inputs(inputs) == inputs
                assert source_inputs(model['inputs']) == model['inputs'] and sha(ROOT / model['binary']) == model['binary_sha256']
                result['cases'].append(row)
                dump(FOLDER / 'report.json', result)
                print('PASS', variant, iterations, cycles, 'IPC', row['ipc'], 'CM/MHz', row['coremark_per_mhz_estimate'],
                      'static V', len(static_vector), flush=True)
    result['passed'] = True
    dump(FOLDER / 'report.json', result)


if __name__ == '__main__':
    main()

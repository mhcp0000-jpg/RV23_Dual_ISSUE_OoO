"""Compare guest segment fault-only-first and whole-register replay with Sail."""
import argparse
import json

from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/guest_vector_segment_ff'
BASE = 'sw/tests/rv64_hypervisor_vector_faults.S'
BODY = 'sw/tests/rv64_guest_vector_segment_ff_body.S'
WHOLE_FOLDER = 'out/rva23/guest_vector_whole'
WHOLE_BODY = 'sw/tests/rv64_guest_vector_whole_body.S'
CONFIG = 'config/reference/sail-rv23.json'
LINKER = 'scripts/reference/upstream_htif.ld'
REFERENCE = 'out/reference/sail-event-driver/report.json'


def fixture(body=BODY):
    original = (ROOT / BASE).read_text(encoding='utf-8')
    header = original.split('guest_entry:\n', 1)[0]
    superpage = ('  li t0,(0x20000000 >> 2) | 0xcf\n'
                 '  sd t0,0(t1)                  # guest 0x40000000 -> SRAM 0x80000000')
    assert header.count(superpage) == 1
    header = header.replace(superpage, '''  li t0,(0x10002000 >> 2) | 1
  sd t0,0(t1)
  la t1,vsdata_l0
  li t0,(0x20000000 >> 2) | 0xcf
  li t2,256
init_vsdata:
  sd t0,0(t1)
  addi t1,t1,8
  addi t0,t0,1024
  addi t2,t2,-1
  bnez t2,init_vsdata''')
    vs_table_map = '  sd t0,8(t1)\n  la t0,groot\n'
    assert header.count(vs_table_map) == 1
    header = header.replace(vs_table_map, '''  sd t0,8(t1)
  la t0,vsdata_l0
  srli t0,t0,2
  ori t0,t0,0x53
  sd t0,16(t1)
  la t0,groot
''')
    header = header.replace('  li t0,(0x800a4000 >> 2) | 0xdb\n'
                            '  sd t0,1312(t1)            # G-stage W denied on the second data page',
                            '  sd zero,1312(t1)          # G-stage page absent')
    assert 'sd zero,1312(t1)' in header
    begin = header.index('  li t0,0x800a3ff0\n')
    end = header.index('  la t0,guest_entry\n', begin)
    if body == WHOLE_BODY:
        values = ['  li t0,0x800a3fe0']
        for index, value in enumerate(range(101, 109)):
            values.extend((f'  li t1,{value}', f'  sd t1,{8 * index}(t0)'))
    else:
        values = ['  li t0,0x800a3ff0']
        for index, value in enumerate((101, 102, 103, 104, 201, 202, 203, 204, 205, 206, 207)):
            values.extend((f'  li t1,{value}', f'  sw t1,{4 * index}(t0)'))
    return (header[:begin] + '\n'.join(values) + '\n  li s5,0\n' + header[end:] +
            (ROOT / body).read_text(encoding='utf-8') + '\n' + original[original.index('.section .bss'):] +
            '\nvsdata_l0:.skip 4096\n')


def verify_traces(sail_trace, rtl_trace, *, whole=False):
    sail_rows, rows = read_csv(sail_trace), read_csv(rtl_trace)
    count, mismatch = compare(sail_rows, rows)
    assert mismatch is None, mismatch
    traps = [row for row in rows if row['trap'] == '1' and int(row['pc'], 16) >= 0x40000000]
    if whole:
        return verify_whole(rows, traps, count)
    assert [(int(row['cause']), int(row['tval'], 16)) for row in traps] == [
        (21, 0x400a4000), (10, 0), (13, 0x400a4000), (10, 0)]
    # NF=2, MOP=unit stride, LUMOP=fault-only-first, width=e32, vd=v8, rs1=s0.
    probes = [row for row in rows if int(row['instruction'], 16) & ~(1 << 25) == 0x21046407]
    assert [(row['trap'], bool(int(row['instruction'], 16) & (1 << 25))) for row in probes] == [
        ('0', True), ('0', True), ('0', False), ('1', True), ('0', True)] * 2, probes
    for index in (0, 1):
        assert probes[5 * index + 3]['pc'] == probes[5 * index + 4]['pc'] == traps[2 * index]['pc']
    return dict(matched_events=count, traps=traps, probe_pcs=[row['pc'] for row in probes])


def verify_whole(rows, traps, count):
    assert [(int(row['cause']), int(row['tval'], 16)) for row in traps] == [
        (21, 0x400a4000), (10, 0), (23, 0x400a4000), (10, 0),
        (13, 0x400a4000), (10, 0), (15, 0x400a4000), (10, 0)]
    load, store = '62847407', '62840427'
    probes = [row for row in rows if row['instruction'] in (load, store)]
    assert [(row['instruction'], row['trap']) for row in probes] == [
        (load, '1'), (load, '0'), (store, '1'), (store, '0')] * 2, probes
    for fault, retry, trap in zip(probes[::2], probes[1::2], traps[::2], strict=True):
        assert fault['pc'] == retry['pc'] == trap['pc']
    return dict(matched_events=count, traps=traps, probe_pcs=[row['pc'] for row in probes])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--whole-register', action='store_true')
    whole = parser.parse_args().whole_register
    body = WHOLE_BODY if whole else BODY
    folder = ROOT / (WHOLE_FOLDER if whole else FOLDER)
    folder.mkdir(parents=True, exist_ok=True)
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_bytes())
    reference = json.loads((ROOT / REFERENCE).read_bytes())
    assert reference['passed'] and {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1', '-GHAS_MMU=1'} <= set(model['params'])
    runtime = {**reference['inputs'], reference['binary']: reference['binary_sha256'],
               **source_inputs([BASE, body, CONFIG, LINKER, REFERENCE, 'scripts/run_sail_event_comparison.py',
                                'tb/fixtures/bootrom/bootrom_host_jump64.hex'])}
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    source, elf, trace, sail_trace = (folder / name for name in ('test.S', 'test.elf', 'commit.csv', 'sail.csv'))

    def fresh():
        for path, digest in inputs.items():
            assert sha(ROOT / path) == digest, path

    fresh()
    source.write_text(fixture(body), encoding='utf-8')
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none', '-T', LINKER,
            source, '-o', elf], folder / 'compile.log', 60)
        elf_digest = sha(elf)
        original_path = sim.env['PATH']
        sim.env['PATH'] = 'C:/rv_toolchains/cygwin-rv23/bin;' + original_path
        sail, sail_log = sim.run([ROOT / reference['binary'], '--config', ROOT / CONFIG,
            '--commit-csv', sail_trace, '--inst-limit', '100000', elf], folder / 'sail.log', 120)
        sim.env['PATH'] = original_path
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit', '+htif',
            '+timeout_cycles=150000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    fresh()
    assert sha(elf) == elf_digest
    assert 'PASS Sail HTIF' in sail_log and '[host-finish code=0]' in log and 'PASS rv32_program_tb' in log
    outcomes = verify_traces(sail_trace, trace, whole=whole)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=elf_digest,
        trace_sha256=sha(trace), sail_trace_sha256=sha(sail_trace), compile=compile_run,
        run=run, sail=sail, outcomes=outcomes))
    scope = ('whole-register load/store: four VS/G same-PC retries' if whole else
             'segment fault-only-first: eight VS/G probes and two same-PC retries')
    print(f'PASS guest {scope}, {outcomes["matched_events"]} matching Sail/RTL events', flush=True)


if __name__ == '__main__':
    main()

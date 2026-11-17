"""Compare guest instruction fetch after batched HINVAL and SINVAL remaps."""
import json

import run_guest_vector_segment_ff as guest_paging
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/guest_ifetch_inval'
BODY = 'sw/tests/rv64_guest_ifetch_inval_body.S'
VIRTUAL_PC = (0x400a3000, 0x400a4000)


def fixture():
    guest = guest_paging.fixture()
    header = guest.split('guest_entry:\n', 1)[0]
    before_entry = '  la t0,guest_entry\n'
    assert header.count(before_entry) == 1
    data_setup = header.index('  li t0,0x800a3ff0\n')
    entry = header.index(before_entry, data_setup)
    header = header[:data_setup] + '  j install_ifetch_fixture\nenter_ifetch_guest:\n' + header[entry:]
    return header + (ROOT / BODY).read_text(encoding='utf-8') + '\n' + guest[guest.index('.section .bss'):]


def reference_config():
    config = json.loads((ROOT / guest_paging.CONFIG).read_bytes())
    config['memory']['vmidlen'] = 0
    return config


def verify_traces(sail_trace, rtl_trace):
    rows = read_csv(rtl_trace)
    count, mismatch = compare(read_csv(sail_trace), rows)
    assert mismatch is None, mismatch
    events = []
    for row in rows:
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if pc in VIRTUAL_PC:
            value = int(row['wdata'], 16)
            assert row['trap'] == '0' and row['rd_write'] == '1' and int(row['rd']) == 10
            assert word == ((value << 20) | 0x513)
            events.append([pc, value])
        elif word in (0x18000073, 0x18100073) or word & 0xfe007fff in (0x66000073, 0x26000073, 0x16000073):
            assert row['trap'] == '0'
            events.append([word])
    expected = [[VIRTUAL_PC[0], 41], [VIRTUAL_PC[1], 82],
                [0x18000073], [0x67c30073], [0x67c38073], [0x18100073],
                [VIRTUAL_PC[0], 82], [VIRTUAL_PC[1], 123],
                [0x18000073], [0x26640073], [0x26648073], [0x18100073],
                [VIRTUAL_PC[0], 123], [VIRTUAL_PC[1], 82],
                [0x18000073], [0x16640073], [0x16648073], [0x18100073],
                [VIRTUAL_PC[0], 82], [VIRTUAL_PC[1], 123]]
    assert events == expected, events
    traps = [int(row['cause']) for row in rows if row['trap'] == '1' and int(row['pc'], 16) >= 0x40000000]
    assert traps == [10, 10, 10]
    return dict(matched_events=count, boundary_events=events, traps=traps)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_bytes())
    reference = json.loads((ROOT / guest_paging.REFERENCE).read_bytes())
    assert reference['passed'] and {'-GXLEN=64', '-GHAS_H=1', '-GHAS_MMU=1', '-GHAS_SVINVAL=1'} <= set(model['params'])
    config = folder / 'sail.json'
    dump(config, reference_config())
    runtime = {**reference['inputs'], reference['binary']: reference['binary_sha256'],
               **source_inputs([BODY, guest_paging.BASE, guest_paging.BODY, guest_paging.CONFIG,
                                guest_paging.LINKER, guest_paging.REFERENCE, 'scripts/run_guest_vector_segment_ff.py',
                                'scripts/run_sail_event_comparison.py', 'tb/fixtures/bootrom/bootrom_host_jump64.hex',
                                config.relative_to(ROOT).as_posix()])}
    source, elf, trace, sail_trace = (folder / name for name in ('test.S', 'test.elf', 'commit.csv', 'sail.csv'))
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path
    source.write_text(fixture(), encoding='utf-8')
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh_svinval', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none', '-T', guest_paging.LINKER,
            source, '-o', elf], folder / 'compile.log', 60)
        elf_digest = sha(elf)
        original_path = sim.env['PATH']
        sim.env['PATH'] = 'C:/rv_toolchains/cygwin-rv23/bin;' + original_path
        sail, sail_log = sim.run([ROOT / reference['binary'], '--config', config,
            '--commit-csv', sail_trace, '--inst-limit', '100000', elf], folder / 'sail.log', 120)
        sim.env['PATH'] = original_path
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit', '+htif',
            '+timeout_cycles=150000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    assert sha(elf) == elf_digest
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path
    assert 'PASS Sail HTIF' in sail_log and '[host-finish code=0]' in log and 'PASS rv32_program_tb' in log
    outcomes = verify_traces(sail_trace, trace)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=elf_digest,
        trace_sha256=sha(trace), sail_trace_sha256=sha(sail_trace), compile=compile_run,
        run=run, sail=sail, outcomes=outcomes))
    print(f'PASS batched guest instruction remap: 8 fetches and {outcomes["matched_events"]} Sail/RTL events')


if __name__ == '__main__':
    main()

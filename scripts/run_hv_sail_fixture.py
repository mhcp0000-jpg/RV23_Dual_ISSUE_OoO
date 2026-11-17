"""Build one contract ELF and execute it on Sail and the native H/V SoC."""

import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


REFERENCE = 'out/reference/sail-event-driver/report.json'
CONFIG = 'config/reference/sail-rv23.json'
LINKER = 'scripts/reference/upstream_htif.ld'


def run_fixture(source, folder, generator, verify_traces, *,
                source_dependencies=(), timeout_cycles=100000):
    folder.mkdir(parents=True, exist_ok=True)
    elf, trace, sail_trace = (folder / filename for filename in ('test.elf', 'commit.csv', 'sail.csv'))
    reference = json.loads((ROOT / REFERENCE).read_bytes())
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_bytes())
    assert reference['passed'] and {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(model['params'])
    runtime = source_inputs([source.relative_to(ROOT).as_posix(), REFERENCE, CONFIG, LINKER,
                             'scripts/run_hv_sail_fixture.py', 'scripts/run_sail_event_comparison.py',
                             *source_dependencies,
                             'tb/fixtures/bootrom/bootrom_host_jump64.hex'])
    runtime.update(reference['inputs'])
    runtime[reference['binary']] = reference['binary_sha256']
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path

    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', LINKER, source, '-o', elf], folder / 'compile.log', 60)
        elf_digest = sha(elf)
        host_path = sim.env['PATH']
        sim.env['PATH'] = 'C:/rv_toolchains/cygwin-rv23/bin;' + host_path
        sail, sail_log = sim.run([ROOT / reference['binary'], '--config', CONFIG,
            '--commit-csv', sail_trace, '--inst-limit', '100000', elf], folder / 'sail.log', 120)
        sim.env['PATH'] = host_path
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit', '+htif',
            f'+timeout_cycles={timeout_cycles}', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    assert sha(elf) == elf_digest
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path
    assert 'PASS Sail HTIF' in sail_log and 'PASS rv32_program_tb' in log
    outcomes = verify_traces(sail_trace, trace)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(generator), source_sha256=sha(source), elf_sha256=elf_digest,
        trace_sha256=sha(trace), sail_trace_sha256=sha(sail_trace), compile=compile_run,
        run=run, sail=sail, outcomes=outcomes))
    return outcomes

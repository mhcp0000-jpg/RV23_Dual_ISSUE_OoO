"""Check native PLIC interrupts and ordered vector claims."""

import json
import re

from run_sail_event_comparison import read_csv
from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/vector_irq_boundary'
SOURCE = 'sw/tests/rv64_vector_irq.S'
TESTBENCH = 'tb/rv23_vector_irq_tb.sv'
VECTOR_STORE = 0x02040427
SCALAR_STORE = 0x0144b023
VECTOR_CLAIM = 0x0ccae407  # vloxei32.v v8,(s5),v12,v0.t


def verify(trace, log):
    witness = re.search(r'^VECTOR IRQ first=(\d+) pending=(\d+) pending_bytes=(\d+) '
                        r'last=(\d+) retire=(\d+) trap=(\d+) scalar=(\d+)$', log, re.MULTILINE)
    assert witness and 'PASS rv32_program_tb' in log
    first, pending, pending_bytes, last, retire, trap, scalar = map(int, witness.groups())
    assert first < pending < last < retire < trap and pending_bytes in range(1, 128)
    assert last < scalar
    claims = re.search(r'^PLIC CLAIM ORDER vector=(\d+) scalar=(\d+)$', log, re.MULTILINE)
    assert claims and tuple(map(int, claims.groups())) == (2, 2)
    observed = []
    for row in read_csv(trace):
        if int(row['pc'], 16) < 0x80000000:
            continue
        word = int(row['instruction'], 16)
        if row['trap'] == '1':
            assert int(row['cause']) == 11 and int(row['tval'], 16) == 0
            observed.append('interrupt')
        elif word in (VECTOR_STORE, SCALAR_STORE):
            observed.append('vector_store' if word == VECTOR_STORE else 'scalar_store')
        elif word == VECTOR_CLAIM:
            observed.append('vector_claim')
    expected = (['vector_store', 'scalar_store', 'interrupt'] if scalar < trap else
                ['vector_store', 'interrupt', 'scalar_store'])
    assert observed == [*expected, 'vector_claim']
    return dict(bytes_at_pending=pending_bytes, cycles_pending_to_trap=trap - pending,
                observed_order=observed, vector_claims=2, scalar_claims=2)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    elf, trace = folder / 'test.elf', folder / 'commit.csv'
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', TESTBENCH, 'tb/e2e/dpi/elf_loader.cpp',
    ]
    linker = 'scripts/reference/upstream_htif.ld'
    runtime = source_inputs([SOURCE, linker, 'tb/fixtures/bootrom/bootrom_host_jump64.hex'])
    model_path = folder / 'model.json'
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', linker, ROOT / SOURCE, '-o', elf], folder / 'compile.log', 60)
        elf_digest = sha(elf)
        model = json.loads(model_path.read_bytes()) if model_path.exists() else None
        if not model or model['inputs'] != source_inputs(files) or sha(ROOT / model['binary']) != model['binary_sha256']:
            model = sim.build('rv23_vector_irq', 'rv23_vector_irq_tb', files)
            dump(model_path, model)
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit', '+htif',
            '+timeout_cycles=100000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    assert sha(elf) == elf_digest
    for path, digest in {**model['inputs'], **runtime}.items():
        assert sha(ROOT / path) == digest, path
    outcomes = verify(trace, log)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(__file__), source_sha256=runtime[SOURCE], elf_sha256=elf_digest,
        trace_sha256=sha(trace), compile=compile_run, run=run, outcomes=outcomes))
    print('PASS native PLIC interrupt boundary and ordered claims', outcomes, flush=True)


if __name__ == '__main__':
    main()

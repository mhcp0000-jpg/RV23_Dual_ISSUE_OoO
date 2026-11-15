"""Verify external AXI wake and interference with live LR/SC reservations."""

import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/wrs_debug_wake'
SOURCE = 'sw/tests/rv64_wrs_debug_wake.S'
TESTBENCH = 'tb/rv23_wrs_debug_wake_tb.sv'
WITNESS = 'WRS DEBUG WAKE PASS same_line=4 unrelated=4'
INTERFERENCE_WITNESS = 'LRSC DEBUG INTERFERENCE PASS adjacent=2 overlapping=2'
MARKER = 'data=0x57525344'


def verify_trace(path):
    with path.open(newline='') as stream:
        rows = [row for row in csv.DictReader(stream) if int(row['pc'], 16) >= 0x80000000]
    assert all(row['trap'] == '0' for row in rows)
    outcomes = []
    interference = []
    for row in rows:
        instruction = int(row['instruction'], 16)
        if instruction == 0x00d00073:
            outcomes.append('WRS.NTO')
        elif instruction & 0xf800707f in (0x1000202f, 0x1000302f, 0x1800202f, 0x1800302f):
            assert row['gpr_we'] == '1', row
            mnemonic = ('SC' if instruction & 0x08000000 else 'LR') + ('.D' if instruction & 0x1000 else '.W')
            value = int(row['wdata'], 16)
            if len(outcomes) == 8:
                interference.append([mnemonic, value])
            elif mnemonic.startswith('SC'):
                assert value == 1, row
                outcomes.append(mnemonic)
    assert outcomes == ['WRS.NTO', 'SC.W', 'WRS.NTO', 'SC.D'] * 2
    expected = []
    for width, first_sc in (('W', 0), ('D', 0), ('W', 1), ('D', 1)):
        expected.extend([[f'LR.{width}', 0], [f'SC.{width}', first_sc], [f'SC.{width}', 1]])
    assert interference == expected
    return outcomes, interference


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    elf, trace = folder / 'test.elf', folder / 'commit.csv'
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', TESTBENCH, 'tb/e2e/dpi/elf_loader.cpp']
    runtime = source_inputs(['tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])
    model_path = folder / 'model.json'
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh_zawrs', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', ROOT / SOURCE, '-o', elf], folder / 'compile.log', 60)
        model = json.loads(model_path.read_text(encoding='utf-8')) if model_path.exists() else None
        if not model or model['inputs'] != source_inputs(files) or sha(ROOT / model['binary']) != model['binary_sha256']:
            model = sim.build('rv23_wrs_debug_wake', 'rv23_wrs_debug_wake_tb', files)
            dump(model_path, model)
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=30000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    assert all(marker in log for marker in (WITNESS, INTERFERENCE_WITNESS, MARKER, 'PASS rv32_program_tb'))
    for path, digest in {**model['inputs'], **runtime}.items():
        assert sha(ROOT / path) == digest, path
    outcomes, interference = verify_trace(trace)
    dump(folder / 'report.json', dict(
        passed=True, model=model, runtime_inputs=runtime, generator_sha256=sha(__file__),
        source_sha256=sha(ROOT / SOURCE), elf_sha256=sha(elf), trace_sha256=sha(trace),
        compile=compile_run, run=run, outcomes=outcomes, interference=interference))
    print('PASS WRS debug wake and LR/SC debug interference', flush=True)


if __name__ == '__main__':
    main()


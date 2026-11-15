"""Check coherent PTE cache hits after external debug writes and SFENCE.VMA."""
import json
import subprocess

from sim_runner import ROOT, Simulator, GCC, dump, sha


def main():
    folder = ROOT / 'out/rva23/ptw_debug_coherence'
    folder.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'sw/tests/rv64_ptw_debug_coherence.S'
    runtime = {p:sha(ROOT / p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex',
                                        'sw/benchmarks/coremark/rv32_tim.ld']}
    elf = folder / 'test.elf'
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', 'tb/rv23_ptw_debug_coherence_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        symbols = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), str(elf)], text=True)
        assert any(line.split() == ['0000000080022000', 'b', 'level0'] for line in symbols.splitlines())
        model = sim.build('rv23_ptw_debug_coherence', 'rv23_ptw_debug_coherence_tb', files)
        run, text = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            '+quiet_commit', '+timeout_cycles=1000000', '+expected_exit_code=0',
            f'+trace_file={folder.relative_to(ROOT).as_posix()}/commit.csv'], folder / 'simulation.log', 240)
    assert 'PTW DEBUG COHERENCE PASS' in text and 'PASS rv32_program_tb' in text
    assert 'PTW DEBUG MODES halted=8 running=8' in text
    for path, digest in {**model['inputs'], **runtime}.items():
        assert sha(ROOT / path) == digest, path
    model['passed'] = True
    dump(folder / 'report.json', dict(passed=True, model=model, generator_sha256=sha(__file__),
        scope='Resident PTE updates through debug AXI with running or halted core followed by SFENCE.VMA; finite S-mode coherent PTW coverage',
        runtime_inputs=runtime,
        source_sha256=sha(source), elf_sha256=sha(elf), compile=compile_run, run=run,
        trace_sha256=sha(folder / 'commit.csv')))
    print('PASS native PTW/debug coherence', flush=True)


if __name__ == '__main__':
    main()

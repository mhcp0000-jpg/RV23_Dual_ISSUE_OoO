"""Reject a copied cache that drops snoop updates only for the tested PTE."""
import json

from sim_runner import ROOT, Simulator, dump, sha


def main():
    positive_path = ROOT / 'out/rva23/ptw_debug_coherence/report.json'
    positive = json.loads(positive_path.read_text(encoding='utf-8'))
    assert positive['passed']
    for path, digest in positive['model']['inputs'].items():
        assert sha(ROOT / path) == digest, path
    assert sha(ROOT / positive['model']['binary']) == positive['model']['binary_sha256']
    elf = ROOT / 'out/rva23/ptw_debug_coherence/test.elf'
    assert sha(elf) == positive['elf_sha256']
    folder = ROOT / 'out/negative_controls/ptw_debug_coherence'
    folder.mkdir(parents=True, exist_ok=True)
    original = ROOT / 'rtl/soc/rv23_cache.sv'
    contents = original.read_text(encoding='utf-8')
    anchor = 'wire snoop_update=!READ_ONLY && snoop_resident && (|snoop_wstrb_i);'
    assert contents.count(anchor) == 1
    mutant = folder / 'rv23_cache.sv'
    mutant.write_text(contents.replace(anchor,
        "wire snoop_update=(snoop_addr_i!=32'h80022000) && !READ_ONLY && snoop_resident && (|snoop_wstrb_i);"),
        encoding='utf-8')
    files = [mutant.relative_to(ROOT).as_posix() if path == 'rtl/soc/rv23_cache.sv' else path
             for path in (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines()]
    files += ['tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
              'tb/rv32_program_tb.sv', 'tb/rv23_ptw_debug_coherence_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']
    with Simulator() as sim:
        model = sim.build('rv23_ptw_debug_coherence_negative', 'rv23_ptw_debug_coherence_tb', files)
        run, _ = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            '+quiet_commit', '+timeout_cycles=1000000', '+expected_exit_code=0'], folder / 'simulation.log',
            240, expected_failure='Stale PTE response after update 1:')
    assert sha(original) == positive['model']['inputs']['rtl/soc/rv23_cache.sv']
    dump(folder / 'report.json', dict(passed=True,
        scope='Expected failure: dropping only tested-PTE resident snoop updates is rejected by identical ELF and TB',
        model=model, run=run, generator_sha256=sha(__file__), original_sha256=sha(original),
        mutant_sha256=sha(mutant), elf_sha256=sha(elf), positive_report_sha256=sha(positive_path)))
    print('PASS PTW/debug coherence negative control: stale PTE rejected at first remap', flush=True)


if __name__ == '__main__':
    main()

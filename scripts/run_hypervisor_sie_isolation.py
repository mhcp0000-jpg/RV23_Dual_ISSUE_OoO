"""Same-ELF regression for HS sie leaking virtual interrupt enables."""
import argparse
import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/hypervisor_sie_isolation'
SOURCE = 'sw/tests/rv64_hypervisor_sie_isolation.S'
CSR_RTL = 'rtl/backend/rv_csr_file.sv'
CONTROL_RTL = (FOLDER / 'before/rv_csr_file.sv').relative_to(ROOT).as_posix()


def control_source():
    source = (ROOT / CSR_RTL).read_text(encoding='utf-8')
    masked_write = ('12\'h104:mie_q<=(mie_q & ~delegated_supervisor_mask) |\n'
                    '                         (csr_pending_wdata_q & delegated_supervisor_mask);')
    pre_fix_write = "12'h104:mie_q<=(mie_q & ~mideleg_q) | (csr_pending_wdata_q & mideleg_q);"
    assert source.count(masked_write) == 1
    return source.replace(masked_write, pre_fix_write)


def verify_model_pair(current, control):
    assert current['params'] == control['params'] and current['top'] == control['top']
    prior = dict(control['inputs'])
    assert CSR_RTL not in prior
    prior[CSR_RTL] = prior.pop(CONTROL_RTL)
    assert current['inputs'].keys() == prior.keys()
    assert {name for name, digest in prior.items() if current['inputs'][name] != digest} == {CSR_RTL}
    assert (ROOT / CONTROL_RTL).read_text(encoding='utf-8') == control_source()
    for model in (current, control):
        for path, digest in model['inputs'].items():
            assert sha(ROOT / path) == digest, path
        assert sha(ROOT / model['binary']) == model['binary_sha256']


def verify_trace(path, before):
    with path.open(newline='') as stream:
        traps = [row for row in csv.DictReader(stream)
                 if row['trap'] == '1' and int(row['pc'], 16) >= 0x80000000]
    assert [int(row['cause']) for row in traps] == ([10] if before else [10, 10, 10]), traps
    return traps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', action='store_true', help='Capture the known spurious interrupt')
    args = parser.parse_args()
    folder = FOLDER / 'before' if args.before else FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(model['params'])
    runtime = source_inputs([SOURCE, 'tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path
    elf = FOLDER / 'test.elf'
    trace = folder / 'commit.csv'
    with Simulator() as sim:
        if args.before:
            (ROOT / CONTROL_RTL).write_text(control_source(), encoding='utf-8')
            files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
                'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
                'tb/rv32_program_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']
            files[files.index(CSR_RTL)] = CONTROL_RTL
            control = sim.build('rv23_hs_sie_pre_fix', model['top'], files, model['params'])
            verify_model_pair(model, control)
            model = control
            compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh',
                '-mabi=lp64d', '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
                '-T', 'sw/benchmarks/coremark/rv32_tim.ld', ROOT / SOURCE, '-o', elf],
                folder / 'compile.log', 60)
        else:
            previous = json.loads((FOLDER / 'before/report.json').read_text(encoding='utf-8'))
            verify_model_pair(model, previous['model'])
            assert sha(elf) == previous['elf_sha256'] and runtime == previous['runtime_inputs']
            compile_run = previous['compile']
        elf_digest = sha(elf)
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=200000', f'+expected_exit_code={int(args.before)}'],
            folder / 'simulation.log', 120)
    assert ('data=0x42414449' if args.before else 'data=0x48534945') in log
    assert 'PASS rv32_program_tb' in log
    traps = verify_trace(trace, args.before)
    for path, digest in {**inputs, **model['inputs'], model['binary']: model['binary_sha256']}.items():
        assert sha(ROOT / path) == digest, path
    assert sha(elf) == elf_digest
    dump(folder / 'report.json', dict(passed=True, before=args.before, model=model,
        generator_sha256=sha(__file__), runtime_inputs=runtime, elf_sha256=elf_digest,
        trace_sha256=sha(trace), compile=compile_run, run=run, traps=traps))
    print('PASS reproduced spurious HS VSEI' if args.before else 'PASS HS sie isolation and HS/VS VSEI delivery')


if __name__ == '__main__':
    main()

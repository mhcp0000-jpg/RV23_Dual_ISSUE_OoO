"""Exercise constrained LR/SC loops across data and instruction line positions.

Finite progress evidence on the production H/V SoC, not a liveness proof.
The retry region contains only LR, ADDI, SC and BNEZ (four instructions).
"""
import csv
import json

from sim_runner import ROOT, Simulator, GCC, dump, sha, source_inputs


def main():
    folder = ROOT / 'out/rva23/lrsc_progress'
    folder.mkdir(parents=True, exist_ok=True)
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    assert all(p in model['params'] for p in ['-GHAS_H=1', '-GHAS_V=1', '-GXLEN=64'])
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']

    def fresh():
        assert source_inputs(files) == model['inputs']
        assert sha(ROOT / model['binary']) == model['binary_sha256']

    fresh()
    lines = ['.section .text.init,"ax"', '.option norvc', '.option norelax', '.globl _start', '_start:',
             'la t0,fail', 'csrw mtvec,t0']
    cases = []
    # Every naturally aligned W/D address in a 64-byte reservation granule.
    # Move each constrained loop to a line start, middle and final halfword.
    for suffix, size in [('w', 4), ('d', 8)]:
        for offset in range(0, 64, size):
            for position in [0, 32, 62]:
                index = len(cases)
                lines += [f'li s0,0x{0x80070000 + offset:x}', f's{suffix} zero,0(s0)',
                          'li s1,16', f'j setup_{index}', '.balign 64,0',
                          *([f'.space {position}'] if position else []), f'loop_{index}:',
                          f'lr.{suffix}.aq t1,(s0)', 'addi t1,t1,1',
                          f'sc.{suffix}.rl t2,t1,(s0)', f'bnez t2,loop_{index}',
                          'addi s1,s1,-1', f'bnez s1,loop_{index}',
                          f'l{suffix} t1,0(s0)', 'li t2,16', 'bne t1,t2,fail',
                          f'j done_{index}', f'setup_{index}:', f'j loop_{index}',
                          f'done_{index}:']
                cases.append(dict(width=size * 8, data_offset=offset,
                                  instruction_line_offset=position, successes=16))
    lines += ['lui t0,0x10000', 'li t1,0x4c525343', 'sw t1,0xc(t0)',
              'sw zero,0x14(t0)', 'halt:wfi', 'j halt',
              'fail:', 'lui t0,0x10000', 'li t1,1', 'sw t1,0x14(t0)', 'j halt']
    source = folder / 'test.S'
    source.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    elf, trace = folder / 'test.elf', folder / 'commit.csv'
    with Simulator() as sim:
        compile_run, _ = sim.run([
            GCC / 'riscv-none-elf-gcc.exe', '-march=rv64imafdc_zicsr_zifencei', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, text = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=3000000', '+expected_exit_code=0'], folder / 'simulation.log', 240)
    fresh()
    assert 'PASS rv32_program_tb' in text and 'data=0x4c525343' in text
    with trace.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert not [r for r in rows if r['trap'] == '1' and int(r['pc'], 16) >= 0x80000000]
    atomics = [r for r in rows if r['trap'] == '0' and int(r['instruction'], 16) & 0x7f == 0x2f]
    sc = [r for r in atomics if int(r['instruction'], 16) >> 27 == 3]
    lr = [r for r in atomics if int(r['instruction'], 16) >> 27 == 2]
    successes = sum(c['successes'] for c in cases)
    assert len(sc) == len(lr) and len(sc) >= successes
    assert all(r['rd_write'] == '1' and r['rd'] == '7' for r in sc)
    assert sum(int(r['wdata'], 16) == 0 for r in sc) == successes
    assert all(int(r['pc'], 16) == int(load['pc'], 16) + 8 for load, r in zip(lr, sc))
    # Every declared placement must actually retire, including halfword-aligned
    # 32-bit instructions straddling a 64-byte instruction-cache line.
    for width in [32, 64]:
        for position in [0, 32, 62]:
            matching = [r for r in lr if int(r['pc'], 16) % 64 == position and
                        ((int(r['instruction'], 16) >> 12) & 7) == (2 if width == 32 else 3)]
            assert len(matching) >= (64 // (width // 8)) * 16, (width, position)
    dump(folder / 'report.json', dict(passed=True,
        scope='Finite constrained LR/SC progress for all W/D positions in one reservation granule and three instruction-line positions; no universal liveness proof',
        model=model, generator_sha256=sha(__file__), cases=cases,
        successful_updates=successes, lr_retirements=len(lr), sc_retirements=len(sc),
        source_sha256=sha(source), elf_sha256=sha(elf), trace_sha256=sha(trace),
        compile=compile_run, run=run))
    print('PASS constrained LR/SC progress:', len(cases), 'placements,', successes,
          'successful updates,', len(sc), 'SC attempts', flush=True)


if __name__ == '__main__':
    main()

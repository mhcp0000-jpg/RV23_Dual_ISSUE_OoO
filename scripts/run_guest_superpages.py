"""Verify aligned and misaligned VS-stage and G-stage superpages on the H/V SoC."""
import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/guest_superpages'
BASE = 'sw/tests/rv64_hypervisor_gstage.S'
MARKER = 'data=0x53555047'
SRAM = 0x80000000
OFFSETS = (0xa0018, 0xe1020)
VALUES = (0x13579bdf2468ace0, 0xfedcba9876543210)
STORE_READBACK = 0x0123456789abcdef
G_BASE = (3 << 39) | 0x40000000
VS_BASE = 0x40000000
CASES = [(stage, level, G_BASE if stage == 'G' else VS_BASE)
         for stage in ('G', 'VS') for level in (1, 2)]


def fixture():
    base = (ROOT / BASE).read_text(encoding='utf-8')
    setup = base.split('hs_entry:\n', 1)[0]
    lines = [setup, 'hs_entry:', 'li t0,0x100', 'csrw hstatus,t0', 'li s3,0']
    for offset, value in zip(OFFSETS, VALUES):
        lines += [f'li t0,{SRAM + offset:#x}', f'li t1,{value:#x}', 'sd t1,0(t0)']
    for index, (stage, level, address) in enumerate(CASES, 1):
        root, child, flags = ('groot', 'glevel1', 0xdf) if stage == 'G' else ('vsroot', 'vslevel1', 0xcf)
        slot = ((address >> 30) & (0x7ff if stage == 'G' else 0x1ff)) * 8
        lines += [f'li s0,{index}', 'csrw vsatp,zero']
        if stage == 'VS':
            lines += ['la t0,groot', f'li t1,{(SRAM >> 2) | 0xdf:#x}', 'sd t1,16(t0)',
                      'la t0,vsroot', 'srli t0,t0,12', 'li t1,0x8000000000000000',
                      'or t0,t0,t1', 'csrw vsatp,t0']
        lines += [f'la s4,{root}', f'li t1,{slot}', 'add s4,s4,t1']
        if level == 1:
            lines += [f'la t0,{child}', 'srli t1,t0,2', 'ori t1,t1,1', 'sd t1,0(s4)', 'mv s4,t0']
        pte = (SRAM >> 2) | flags
        lines += [f'li t1,{pte:#x}', 'sd t1,0(s4)', 'hfence.gvma', 'hfence.vvma']
        for offset, value in zip(OFFSETS, VALUES):
            lines += [f'li t0,{address + offset:#x}', 'hlv.d t1,(t0)',
                      f'li t2,{value:#x}', 'bne t1,t2,fail']
        test_address = address + OFFSETS[1]
        lines += [f'li s1,{test_address:#x}', f'li s8,{SRAM + OFFSETS[1]:#x}',
                  f'li s7,{STORE_READBACK:#x}', 'hsv.d s7,(s1)',
                  'ld a4,0(s8)', 'bne a4,s7,fail']
        # Corrupt PPN[0] for a megapage and PPN[1] for a gigapage.
        broken = pte | (1 << (10 if level == 1 else 19))
        load_cause, store_cause = (21, 23) if stage == 'G' else (13, 15)
        lines += [f'li t1,{broken:#x}', 'sd t1,0(s4)', 'hfence.gvma', 'hfence.vvma',
                  f'li s5,{test_address >> 2 if stage == "G" else 0:#x}',
                  f'li s2,{load_cause}', f'la s6,load_fault_{index}',
                  f'load_fault_{index}: hlv.d t1,(s1)', f'li t0,{2 * index - 1}', 'bne s3,t0,fail',
                  f'li s2,{store_cause}', f'la s6,store_fault_{index}',
                  f'store_fault_{index}: hsv.d zero,(s1)', f'li t0,{2 * index}', 'bne s3,t0,fail',
                  'ld a4,0(s8)', 'bne a4,s7,fail', f'li t1,{VALUES[1]:#x}', 'sd t1,0(s8)']
    lines += ['lui t0,0x10000', 'li t1,0x53555047', 'sw t1,0xc(t0)', 'sw zero,0x14(t0)',
              'halt: j halt',
              'hs_trap:', 'csrr t0,scause', 'bne t0,s2,fail',
              'csrr t0,stval', 'bne t0,s1,fail', 'csrr t0,htval', 'bne t0,s5,fail',
              'csrr t0,htinst', 'bnez t0,fail', 'csrr t0,hstatus', 'andi t0,t0,0x40', 'beqz t0,fail',
              'csrr t0,sepc', 'bne t0,s6,fail', 'addi t0,t0,4', 'csrw sepc,t0',
              'addi s3,s3,1', 'sret',
              'fail:', 'lui t0,0x10000', 'sw s0,0xc(t0)', 'li t1,1', 'sw t1,0x14(t0)', 'j halt',
              base[base.index('.section .bss'):]]
    return '\n'.join(lines) + '\n'


def verify_trace(path):
    with path.open(newline='') as stream:
        rows = [row for row in csv.DictReader(stream) if int(row['pc'], 16) >= SRAM]
    reads = [int(row['wdata'], 16) for row in rows
             if row['trap'] == '0' and int(row['instruction'], 16) == 0x6c02c373]
    assert reads == list(VALUES) * len(CASES), reads
    stores = [row for row in rows if int(row['instruction'], 16) == 0x6f74c073 and row['trap'] == '0']
    assert len(stores) == len(CASES)
    readbacks = [int(row['wdata'], 16) for row in rows
                 if row['trap'] == '0' and int(row['instruction'], 16) == 0x000c3703]
    assert readbacks == [STORE_READBACK] * (2 * len(CASES)), readbacks
    traps = [row for row in rows if row['trap'] == '1']
    assert [int(row['cause']) for row in traps] == [21, 23, 21, 23, 13, 15, 13, 15], traps
    assert [int(row['tval'], 16) for row in traps] == [base + OFFSETS[1] for _, _, base in CASES for _ in range(2)]
    assert len({row['pc'] for row in traps}) == 2 * len(CASES)
    return dict(loads=reads, stores=len(stores), readbacks=readbacks, traps=traps)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source, elf, trace = (folder / name for name in ('test.S', 'test.elf', 'commit.csv'))
    source.write_text(fixture(), encoding='utf-8')
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    runtime = source_inputs([BASE, 'tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    assert all(flag in model['params'] for flag in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1', '-GHAS_MMU=1'))
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=300000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    assert MARKER in log and 'PASS rv32_program_tb' in log
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    outcomes = verify_trace(trace)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=sha(elf),
        trace_sha256=sha(trace), compile=compile_run, run=run, outcomes=outcomes))
    print('PASS native guest superpages: 8 reads, 4 stores and 8 precise alignment traps')


if __name__ == '__main__':
    main()

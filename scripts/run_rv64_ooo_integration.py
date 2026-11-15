"""Observe real dual issue/execution and OoO bypass on production RV64 H/V SoC."""
import csv
import re
import subprocess

from sim_runner import ROOT, Simulator, GCC, dump, sha


BANK_WORDS = {0x80020000: 0xfedcba9876543210, 0x80020008: 0x123456789abcdef0}


def verify_cache_pairs(log):
    counts = re.search(r'RV64 CACHE BANKS PASS i_pairs=(\d+) d_pairs=(\d+) sram_reads=(\d+)', log)
    assert counts
    instruction_pairs, data_pairs, sram_reads = map(int, counts.groups())
    pairs = re.findall(r'RV64 D BANK PAIR accept=(\d+) response=(\d+) '
                       r'addr=([\da-f]+)/([\da-f]+) data=([\da-f]+)/([\da-f]+)', log)
    assert instruction_pairs > 0 and len(pairs) == data_pairs > 0 and sram_reads > 0
    for accept, response, addr0, addr1, data0, data1 in pairs:
        assert int(response) == int(accept) + 1
        assert len({addr0, addr1}) == 2
        assert {int(addr0, 16): int(data0, 16), int(addr1, 16): int(data1, 16)} == BANK_WORDS
    return dict(instruction_pairs=instruction_pairs, data_pairs=data_pairs, sram_reads=sram_reads)


def main():
    folder = ROOT / 'out/rva23/rv64_ooo'
    folder.mkdir(parents=True, exist_ok=True)
    mask = (1 << 64) - 1
    a, b, c = 0xf123456789abcdef, 7, 0x0123456789abcdef
    signed_a = a - (1 << 64)
    expected = [('s0', a // b), ('s1', (a // b + c) & mask),
        ('a0', (a + c) & mask), ('a1', a ^ c), ('a2', a | c), ('a3', a & c),
        ('a4', (a - c) & mask), ('a5', (c << 7) & mask), ('a6', a >> 11), ('a7', (signed_a >> 19) & mask)]
    lines = ['.section .text.init,"ax"', '.option norvc', '.option norelax', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'lui t0,0x02000', 'sw zero,0(t0)',
        f'li t0,0x{a:x}', f'li t1,{b}', f'li t2,0x{c:x}', '.balign 64',
        '.globl ooo_div,ooo_dep,ooo_first,ooo_end', 'ooo_div:', 'divu s0,t0,t1',
        'ooo_dep:', 'add s1,s0,t2', 'ooo_first:', 'add a0,t0,t2', 'xor a1,t0,t2',
        'or a2,t0,t2', 'and a3,t0,t2', 'sub a4,t0,t2', 'slli a5,t2,7',
        'srli a6,t0,11', 'srai a7,t0,19', 'ooo_end:']
    for register, value in expected:
        lines += [f'li t3,0x{value:016x}', f'bne {register},t3,fail']
    # Let both loads queue behind an older store whose address is unresolved.
    # The store resolves to the next cache line and cannot forward either load.
    lines += ['la s2,bank_data', 'ld zero,0(s2)', 'fence rw,rw', 'li s4,8', 'li t4,1',
              'addi s5,s2,64', 'bank_loop:', 'divu s3,s5,t4', 'sd zero,0(s3)', '.balign 16',
              'ooo_bank_load0:', 'ld t5,0(s2)', 'ooo_bank_load1:', 'ld t6,8(s2)']
    for register, value in zip(('t5', 't6'), BANK_WORDS.values()):
        lines += [f'li t3,0x{value:016x}', f'bne {register},t3,fail']
    lines += ['addi s4,s4,-1', 'bnez s4,bank_loop']
    lines += ['lui t0,0x10000', 'li t1,0x4f4f4f36', 'sw t1,0xc(t0)',
        'sw zero,0x14(t0)', 'halt:j halt', 'fail:', 'lui t0,0x10000',
        'li t1,1', 'sw t1,0x14(t0)', 'j halt', '.section .data,"aw"', '.balign 64', 'bank_data:']
    lines += [f'.dword 0x{value:016x}' for value in BANK_WORDS.values()]
    source, elf = folder / 'test.S', folder / 'test.elf'
    source.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    runtime = {p:sha(ROOT / p) for p in ['tb/fixtures/bootrom/bootrom_host_jump64.hex',
                                        'sw/benchmarks/coremark/rv32_tim.ld']}
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', 'tb/rv23_rv64_ooo_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        names = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), str(elf)], text=True)
        symbols = {p[2]:int(p[0],16) for line in names.splitlines() if len(p:=line.split())==3 and p[2].startswith('ooo_')}
        bank_load_pcs = [symbols.pop(f'ooo_bank_load{index}') for index in range(2)]
        assert len(symbols) == 4
        model = sim.build('rv23_rv64_ooo', 'rv23_rv64_ooo_tb', files)
        args = [f'+ooo_{name[4:]}_pc={value:x}' for name,value in symbols.items()]
        args += [f'+ooo_trace={folder.relative_to(ROOT).as_posix()}/pipeline.csv']
        run, text = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            '+quiet_commit', '+timeout_cycles=1000000', '+expected_exit_code=0', *args,
            f'+trace_file={folder.relative_to(ROOT).as_posix()}/commit.csv'], folder / 'simulation.log', 240)
    assert 'RV64 OOO PASS' in text and 'PASS rv32_program_tb' in text and 'data=0x4f4f4f36' in text
    cache_banks = verify_cache_pairs(text)
    for path, digest in {**model['inputs'], **runtime}.items():
        assert sha(ROOT / path) == digest
    with (folder / 'pipeline.csv').open(newline='') as stream:
        events = list(csv.DictReader(stream))
    issued = [r for r in events if r['event']=='issue']
    retired = [r for r in events if r['event']=='retire']
    assert len(issued) == len(retired) == 10
    assert [int(r['pc'],16) for r in retired] == list(range(symbols['ooo_div'], symbols['ooo_end'], 4))
    match = re.search(r'RV64 OOO PASS dual_issue=(\d+) dual_execute=(\d+) dual_retire=(\d+) young_bypass=(\d+) issue_cycles=(\d+)/(\d+)/(\d+)', text)
    assert match
    coverage = dict(zip(['dual_issue','dual_execute','dual_retire','young_bypass','div_issue_cycle','first_young_issue_cycle','dependent_issue_cycle'], map(int,match.groups())))
    assert all(coverage[key]>0 for key in ['dual_issue','dual_execute','dual_retire','young_bypass'])
    model['passed'] = True
    dump(folder / 'report.json', dict(passed=True, scope='Directed RV64 H/V OoO bypass, dual issue/execute/retire, in-order 64-bit results and simultaneous I/D cache bank reads',
        model=model, runtime_inputs=runtime, generator_sha256=sha(__file__), source_sha256=sha(source),
        elf_sha256=sha(elf), pipeline_sha256=sha(folder / 'pipeline.csv'), trace_sha256=sha(folder / 'commit.csv'),
        compile=compile_run, run=run, symbols=symbols, coverage=coverage,
        bank_load_pcs=bank_load_pcs, cache_banks=cache_banks,
        expected_writebacks=[dict(register=r,value=f'{v:016x}') for r,v in expected]))
    print('PASS production RV64 H/V OoO integration and cache banks', coverage, cache_banks, flush=True)


if __name__ == '__main__':
    main()

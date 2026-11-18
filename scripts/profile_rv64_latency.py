"""Measure warmed full-core dependency and memory throughput with fixed assembly."""
import json
import re
import argparse

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeat', action='store_true', help='Repeat the exact ELF and require identical measured cycles')
    args = parser.parse_args()
    folder = ROOT / 'out/performance/rv64_latency'
    folder.mkdir(parents=True, exist_ok=True)
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_bytes())
    assert source_inputs(model['inputs']) == model['inputs']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    cases = [
        ('alu_chain', ['addi a0,a0,1'], 128, ['li a0,7'], ['li t0,263', 'bne a0,t0,fail']),
        ('independent_alu', ['addi t3,s0,1', 'addi t4,s0,2'], 256, [],
         ['addi t0,s0,1', 'bne t3,t0,fail', 'addi t0,s0,2', 'bne t4,t0,fail']),
        ('independent_alu_zero_source', ['addi t3,zero,1', 'addi t4,zero,2'], 256, [],
         ['li t0,1', 'bne t3,t0,fail', 'li t0,2', 'bne t4,t0,fail']),
        ('dependent_ld', ['ld a0,0(a0)'], 128, ['la a0,self_data'], ['la t0,self_data', 'bne a0,t0,fail']),
        ('dual_ld_different_banks', ['ld t3,0(s0)', 'ld t4,8(s0)'], 256, [], ['li t0,123', 'bne t3,t0,fail', 'li t0,456', 'bne t4,t0,fail']),
        ('dual_ld_same_bank', ['ld t3,0(s0)', 'ld t4,16(s0)'], 256, [], ['li t0,123', 'bne t3,t0,fail', 'li t0,789', 'bne t4,t0,fail']),
        ('store_stream', ['sd s2,0(s0)'], 128, [], ['ld t0,0(s0)', 'bne t0,s2,fail']),
    ]
    lines = ['.section .text.init,"ax"', '.option norvc', '.option norelax', '.globl _start', '_start:',
             'la t0,fail', 'csrw mtvec,t0', 'li t0,0x02000000', 'sw zero,0(t0)',
             'la s0,data', 'li s1,0x10000000', 'li s2,123']
    for index, (name, body, count, setup, checks) in enumerate(cases):
        lines += [*setup, f'call {name}', 'csrr s7,mcycle', f'call {name}', 'csrr s8,mcycle',
                  'sub s8,s8,s7', *checks, f'li t0,0x{0x4c415400 + index:08x}', 'sw t0,12(s1)', 'sw s8,12(s1)']
    lines += ['sw zero,20(s1)', 'halt: j halt', 'fail: li t0,1', 'li t1,0x10000000', 'sw t0,20(t1)', 'j halt']
    for name, body, count, setup, checks in cases:
        lines += ['.balign 64', name + ':', '.rept 128', *body, '.endr', 'ret']
    lines += ['.section .data,"aw"', '.balign 64', 'data: .dword 123,456,789', '.balign 64', 'self_data: .dword self_data']
    source, elf = folder / 'test.S', folder / 'test.elf'
    source.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    linker = 'scripts/reference/upstream_htif.ld'
    inputs = source_inputs([source.relative_to(ROOT).as_posix(), linker, 'tb/fixtures/bootrom/bootrom_host_jump64.hex'])
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gc', '-mabi=lp64d',
            '-mcmodel=medany', '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', linker, source, '-o', elf], folder / 'compile.log', 120)
        command = [ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
                   '+quiet_commit', '+timeout_cycles=100000', '+expected_exit_code=0']
        elf_digest = sha(elf)
        run, log = sim.run(command, folder / 'simulation.log', 300)
        repeat = None
        if args.repeat:
            again, again_log = sim.run(command, folder / 'repeat_same_elf.log', 300)
            assert 'PASS rv32_program_tb' in again_log
            pattern = r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]'
            assert re.findall(pattern, log) == re.findall(pattern, again_log)
            assert sha(elf) == elf_digest
            repeat = dict(passed=True, elf_sha256=elf_digest, run=again)
    assert 'PASS rv32_program_tb' in log
    values = [int(value, 16) for value in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]', log)]
    assert len(values) == 2 * len(cases) and values[::2] == list(range(0x4c415400, 0x4c415400 + len(cases)))
    measured = [dict(name=case[0], operations=case[2], cycles=cycles, cycles_per_operation=cycles / case[2])
                for case, cycles in zip(cases, values[1::2])]
    assert source_inputs(model['inputs']) == model['inputs'] and source_inputs(inputs) == inputs
    dump(folder / 'report.json', dict(passed=True, scope='Warm full-core assembly probes; includes call/return/CSR and frontend/layout overhead, not isolated cache latency',
        driver_sha256=sha(__file__), model=model, inputs=inputs, elf_sha256=sha(elf), compile=compile_run, run=run, repeat=repeat, cases=measured))
    print('PASS warmed RV64 full-core latency probes', measured)


if __name__ == '__main__':
    main()

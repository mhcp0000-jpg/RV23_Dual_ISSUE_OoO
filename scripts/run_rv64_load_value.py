"""Compare RV64 OoO loads after mixed-size overlapping stores against Sail and a byte oracle."""
import itertools
import json

from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/rv64_load_value'
CONFIG = 'config/reference/sail-rv23.json'
LINKER = 'scripts/reference/upstream_htif.ld'
SAIL_REPORT = 'out/reference/sail-event-driver/report.json'
STORES = {1: 'sb', 2: 'sh', 4: 'sw', 8: 'sd'}
LOADS = (('ld', 't3', 28, 0, 8, False), ('ld', 't4', 29, 8, 8, False),
         ('ld', 'a0', 10, 4, 8, False), ('lwu', 'a1', 11, 4, 4, False),
         ('lb', 'a2', 12, 7, 1, True), ('lbu', 'a3', 13, 7, 1, False))


def fixture():
    code = ['.section .text.init,"ax"', '.option norvc', '.option norelax', '.globl _start',
            '_start:', 'lui t0,0x02000', 'sw zero,0(t0)', 'la t0,fail', 'csrw mtvec,t0', 'li t6,3']
    cases = []
    geometry = itertools.product((0, 8, 56), STORES, STORES, ('address', 'data'))
    for index, (line_offset, first_width, second_width, delayed) in enumerate(geometry):
        address = 0x80080000 + 128 * index + line_offset
        old = 0x123456789abcdef0 ^ index
        first = 0xf1e2d3c4b5a69788 ^ index
        second = 0x8192a3b4c5d6e7f8 ^ index
        other = 0xfedcba9876543210 ^ index
        # Both overlapping stores end at byte 7. The other store is in the
        # adjacent bank or the next cache line of a 16-byte window.
        first_offset, second_offset = 8 - first_width, 8 - second_width
        code += [f'li s0,{address:#x}', f'li t0,{old:#x}', 'sd t0,0(s0)', 'sd t0,8(s0)', 'fence rw,rw',
                 f'li t0,{first:#x}', f'li t2,{second:#x}', f'li s1,{other:#x}']
        if delayed == 'address':
            code += [f'li t5,{3 * (address + second_offset):#x}', 'divu t1,t5,t6',
                     f'{STORES[first_width]} t0,{first_offset}(s0)', f'{STORES[second_width]} t2,0(t1)']
        else:
            # The truncated result remains the same as the full sentinel.
            dividend = 3 * (second & ((1 << (8 * second_width)) - 1))
            if second_width == 8:
                dividend = 3 * (second >> 2)
                code += [f'li t5,{dividend:#x}', 'divu t1,t5,t6', 'slli t1,t1,2', 'andi t2,t2,3',
                         'or t1,t1,t2']
            else:
                code += [f'li t5,{dividend:#x}', 'divu t1,t5,t6']
            code += [f'{STORES[first_width]} t0,{first_offset}(s0)',
                     f'{STORES[second_width]} t1,{second_offset}(s0)']
        code += ['sd s1,8(s0)']

        ram = bytearray(old.to_bytes(8, 'little') * 2)
        for offset, width, value in ((first_offset, first_width, first), (second_offset, second_width, second),
                                     (8, 8, other)):
            ram[offset:offset + width] = value.to_bytes(8, 'little')[:width]
        expected = []
        for mnemonic, register, rd, offset, width, signed in LOADS:
            code.append(f'{mnemonic} {register},{offset}(s0)')
            value = int.from_bytes(ram[offset:offset + width], 'little', signed=signed) & ((1 << 64) - 1)
            expected.append([rd, value])
        for (_, register, *_), (_, value) in zip(LOADS, expected, strict=True):
            code += [f'li t0,{value:#x}', f'bne {register},t0,fail']
        cases.append(dict(address=address, line_offset=line_offset, first_width=first_width,
                          second_width=second_width, delayed=delayed, loads=expected))
    code += ['li t1,1', 'j finish', 'fail:', 'li t1,3', 'finish:', 'la t0,tohost',
             'sd t1,0(t0)', '1: j 1b', '.section .tohost,"aw"', '.balign 8',
             '.globl tohost,fromhost', 'tohost: .dword 0', 'fromhost: .dword 0']
    return '\n'.join(code) + '\n', cases


def verify_traces(reference, trace, cases):
    rows = read_csv(trace)
    matched, mismatch = compare(read_csv(reference), rows)
    assert mismatch is None, mismatch
    rows = [row for row in rows if int(row['pc'], 16) >= 0x80000000]
    assert not any(row['trap'] == '1' for row in rows)
    loads = [[int(row['rd']), int(row['wdata'], 16)] for row in rows
             if int(row['instruction'], 16) & 0x7f == 0x03 and row['rd_write'] == '1']
    assert loads == [value for case in cases for value in case['loads']], 'Retired load values differ from byte oracle'
    return dict(matched_events=matched, load_count=len(loads))


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source, elf, reference, trace = (folder / name for name in ('test.S', 'test.elf', 'sail.csv', 'commit.csv'))
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_bytes())
    sail = json.loads((ROOT / SAIL_REPORT).read_bytes())
    assert sail['passed'] and {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1', '-GHAS_MISALIGNED=1'} <= set(model['params'])
    runtime = {**sail['inputs'], sail['binary']: sail['binary_sha256'],
               **source_inputs([CONFIG, LINKER, SAIL_REPORT, 'scripts/run_sail_event_comparison.py',
                                'tb/fixtures/bootrom/bootrom_host_jump64.hex'])}
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}

    def fresh():
        for path, digest in inputs.items():
            assert sha(ROOT / path) == digest, path

    fresh()
    code, cases = fixture()
    source.write_text(code, encoding='utf-8')
    with Simulator() as sim:
        compiled, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none', '-T', LINKER,
            source, '-o', elf], folder / 'compile.log', 60)
        elf_digest = sha(elf)
        original_path = sim.env['PATH']
        sim.env['PATH'] = 'C:/rv_toolchains/cygwin-rv23/bin;' + original_path
        ref_run, ref_log = sim.run([ROOT / sail['binary'], '--config', ROOT / CONFIG,
            '--commit-csv', reference, '--inst-limit', '100000', elf], folder / 'sail.log', 120)
        sim.env['PATH'] = original_path
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit', '+htif',
            '+timeout_cycles=400000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    fresh()
    assert sha(elf) == elf_digest
    assert 'PASS Sail HTIF' in ref_log and '[host-finish code=0]' in log and 'PASS rv32_program_tb' in log
    outcomes = verify_traces(reference, trace, cases)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=elf_digest,
        trace_sha256=sha(trace), sail_trace_sha256=sha(reference), compile=compiled, run=run,
        sail=ref_run, cases=cases, outcomes=outcomes))
    print(f'PASS RV64 load values: {len(cases)} mixed-size cases, '
          f'{outcomes["load_count"]} oracle loads, {outcomes["matched_events"]} Sail events', flush=True)


if __name__ == '__main__':
    main()

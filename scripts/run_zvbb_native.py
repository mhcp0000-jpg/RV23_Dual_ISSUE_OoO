"""Exercise each Zvbb form with full vector-register readback on the RV64 SoC."""
import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs
from vector_integer_reference import calculate


FOLDER = 'out/rva23/zvbb_native'
TABLE = 'config/vector_opcode_tables/encodings.json'
ORACLE = 'scripts/vector_integer_reference.py'
MARKER = 'data=0x5a564242'
MODES = ('full', 'masked_restart', 'zero_vl')
INITIAL = bytes([0xa5]) * 64


def fixture():
    table = json.loads((ROOT / TABLE).read_text(encoding='utf-8'))
    forms = [entry['name'] for entry in table['instructions'] if entry['extension'] == 'ZVBB']
    assert len(forms) == len(set(forms)) == 16
    lines = ['.section .text.init,"ax"', '.option norvc', '.option norelax', '.globl _start',
             '_start:', 'la t0,fail', 'csrw mtvec,t0', 'li t0,0x600', 'csrs mstatus,t0',
             'la t0,mask_data', 'vl1re8.v v0,(t0)']
    data = ['.section .data,"aw"', '.balign 16', 'mask_data: .byte 2', '.zero 15',
            'initial: .fill 64,1,0xa5']
    cases = []
    for width in (8, 16, 32, 64):
        lane_bytes = width // 8
        bitmask = (1 << width) - 1
        source = [0, 0x81c1a50789abcdef & bitmask, 1 << (width - 1), bitmask]
        counts = [0, width + 3, width - 1, 2 * width - 1]
        for name, values in [('a', source), ('b', counts)]:
            packed = b''.join((value & bitmask).to_bytes(lane_bytes, 'little') for value in values)
            data += [f'{name}_{width}: .byte ' + ','.join(map(str, packed.ljust(32, b'\0')))]
        lines += [f'la t0,a_{width}', 'vl2re8.v v16,(t0)', f'la t0,b_{width}', 'vl2re8.v v24,(t0)']
        for form in forms:
            operation, operand_form = form.split('.')
            widening = operation == 'vwsll'
            if widening and width == 64:
                continue
            operand = {'v': '', 'vv': ',v24', 'vx': ',a0',
                       'vi': ',63' if operation == 'vror' else ',31'}[operand_form]
            b = {'v': [0] * 4, 'vv': counts, 'vx': [width + 1] * 4,
                 'vi': [63 if operation == 'vror' else 31] * 4}[operand_form]
            output_bytes = lane_bytes * (2 if widening else 1)
            for mode in MODES:
                vl = {'full': 4, 'masked_restart': 3, 'zero_vl': 0}[mode]
                active = {'full': range(4), 'masked_restart': (1,), 'zero_vl': ()}[mode]
                index = len(cases)
                snapshot = bytearray(INITIAL)
                for lane in active:
                    result, _, supported = calculate(operation, width, source[lane], b[lane], 0, 0, 0, 0, 0)
                    assert supported
                    offset = lane * output_bytes
                    snapshot[offset:offset + output_bytes] = result.to_bytes(output_bytes, 'little')
                words = [int.from_bytes(snapshot[i:i+8], 'little') for i in range(0, 64, 8)]
                cases.append(dict(form=form, width=width, mode=mode, words=words))
                lines += [f'li s0,{index}', 'la t0,initial', 'vl4re8.v v8,(t0)',
                          f'vsetivli zero,{vl},e{width},m2,tu,mu', f'li a0,{width + 1}']
                if mode == 'masked_restart':
                    lines += ['csrwi vstart,1']
                suffix = ',v0.t' if mode == 'masked_restart' else ''
                lines += [f'case_{index}: {form} v8,v16{operand}{suffix}', 'csrr a4,vstart',
                          'bnez a4,fail', 'la t0,snapshot', 'vs4r.v v8,(t0)']
                for offset, word in enumerate(words):
                    lines += [f'ld a5,{8 * offset}(t0)', f'li t1,{word:#x}', 'bne a5,t1,fail']
    lines += ['lui t0,0x10000', 'li t1,0x5a564242', 'sw t1,0xc(t0)',
              'sw zero,0x14(t0)', 'halt: j halt', 'fail:', 'lui t0,0x10000',
              'sw s0,0xc(t0)', 'li t1,1', 'sw t1,0x14(t0)', 'j halt',
              *data, '.section .bss,"aw",@nobits', '.balign 16', 'snapshot: .space 64']
    return '\n'.join(lines) + '\n', cases


def verify_trace(trace, cases):
    with trace.open(newline='') as stream:
        rows = [row for row in csv.DictReader(stream) if int(row['pc'], 16) >= 0x80000000]
    assert all(row['trap'] == '0' for row in rows)
    expected_words = [word for case in cases for word in case['words']]
    assert [int(row['wdata'], 16) for row in rows
            if int(row['instruction'], 16) & 0x000fffff == 0x0002b783] == expected_words
    resets = [int(row['wdata'], 16) for row in rows if row['instruction'] == '00802773']
    assert resets == [0] * len(cases)
    return dict(forms=len({case['form'] for case in cases}), cases=len(cases),
                destination_words=len(expected_words))


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source, elf, trace = (folder / name for name in ('test.S', 'test.elf', 'commit.csv'))
    code, cases = fixture()
    source.write_text(code, encoding='utf-8')
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    runtime = source_inputs([TABLE, ORACLE, 'tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    assert all(flag in model['params'] for flag in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'))
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh_zvbb',
            '-mabi=lp64d', '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=1000000', '+expected_exit_code=0'], folder / 'simulation.log', 180)
    assert MARKER in log and 'PASS rv32_program_tb' in log
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    outcomes = verify_trace(trace, cases)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=sha(elf),
        trace_sha256=sha(trace), compile=compile_run, run=run, outcomes=outcomes))
    print('PASS native Zvbb', outcomes)


if __name__ == '__main__':
    main()

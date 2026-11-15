"""Exercise immediate HS/VS interrupt evaluation after CSR writes and SRET."""

import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/interrupt_csr_boundary'
MARKER = 'data=0x49525142'
CSR_ADDRESSES = {'sstatus': 0x100, 'sie': 0x104, 'sip': 0x144}
TRIGGERS = (*CSR_ADDRESSES, 'sret')
CASES = [(mode, trigger) for mode in ('HS', 'VS') for trigger in TRIGGERS]


def fixture():
    lines = [
        '.section .text.init,"ax"', '.option norvc', '.option norelax', '.globl _start',
        '_start:', 'la t0,fail', 'csrw mtvec,t0', 'li t0,-1', 'csrw pmpaddr0,t0',
        'li t0,31', 'csrw pmpcfg0,t0', 'li t0,6', 'csrw mideleg,t0',
        'li t0,4', 'csrw hideleg,t0', 'li t0,0x800', 'csrw mstatus,t0',
        'la t0,hs', 'csrw mepc,t0', 'li s2,0', 'mret',
        'hs:', 'la t0,irq', 'csrw stvec,t0',
    ]
    for index, (mode, trigger) in enumerate(CASES, 1):
        if mode == 'VS' and index == len(TRIGGERS) + 1:
            lines += [
                'csrci sstatus,2', 'la t0,irq', 'csrw vstvec,t0', 'csrw vsstatus,zero',
                'li t0,0x180', 'csrw hstatus,t0', 'la t0,vs', 'csrw sepc,t0',
                'li t0,0x100', 'csrw sstatus,t0', 'sret', 'vs:',
            ]
        lines += [
            f'li s0,{index}', f'la s1,after_{index}', 'csrci sstatus,2',
            'csrci sie,2', 'csrci sip,2',
        ]
        if trigger != 'sip':
            lines += ['csrsi sip,2']
        if trigger != 'sie':
            lines += ['csrsi sie,2']
        if trigger == 'sret':
            lines += ['csrw sepc,s1', 'li t0,0x120', 'csrw sstatus,t0', 'sret', 'j fail']
            clear = 'sstatus'
        else:
            if trigger != 'sstatus':
                lines += ['csrsi sstatus,2']
            lines += [f'csrsi {trigger},2']
            clear = trigger
        lines += [f'after_{index}:', f'csrci {clear},2', 'bne s2,s0,fail']
    lines += [
        'lui t0,0x10000', 'li t1,0x49525142', 'sw t1,0xc(t0)', 'sw zero,0x14(t0)',
        'halt: j halt',
        'irq:', 'csrr t0,scause', 'li t1,0x8000000000000001', 'bne t0,t1,fail',
        'csrr t0,sepc', 'bne t0,s1,fail', 'csrr t0,stval', 'bnez t0,fail',
        'csrr t0,sstatus', 'andi t0,t0,0x122', 'li t1,0x120', 'bne t0,t1,fail',
        'addi s2,s2,1', 'bne s2,s0,fail', 'csrci sip,2', 'sret',
        'fail:', 'lui t0,0x10000', 'sw s0,0xc(t0)', 'li t1,1', 'sw t1,0x14(t0)', 'j halt',
    ]
    return '\n'.join(lines) + '\n'


def verify_trace(path):
    with path.open(newline='') as stream:
        rows = [row for row in csv.DictReader(stream) if int(row['pc'], 16) >= 0x80000000]
    traps = [(index, row) for index, row in enumerate(rows) if row['trap'] == '1']
    assert [int(row['cause']) for _, row in traps] == [1 if mode == 'HS' else 2 for mode, _ in CASES]
    result = []
    for (mode, trigger), (index, row) in zip(CASES, traps):
        pc = int(row['pc'], 16)
        prior = rows[index - 1]
        assert int(row['tval'], 16) == 0
        if trigger == 'sret':
            assert int(prior['instruction'], 16) == 0x10200073
            assert int(prior['pc'], 16) + 8 == pc
            clear = 'sstatus'
        else:
            assert int(prior['instruction'], 16) == (CSR_ADDRESSES[trigger] << 20) | 0x16073
            assert int(prior['pc'], 16) + 4 == pc
            clear = trigger
        resumed = next(item for item in rows[index + 1:] if int(item['pc'], 16) == pc)
        assert resumed['trap'] == '0'
        assert int(resumed['instruction'], 16) == (CSR_ADDRESSES[clear] << 20) | 0x17073
        result.append(dict(mode=mode, trigger=trigger, trace_cause=int(row['cause']), interrupt_pc=row['pc']))
    return result


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source, elf, trace = (folder / name for name in ('test.S', 'test.elf', 'commit.csv'))
    source.write_text(fixture(), encoding='utf-8')
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']
    assert model['inputs'] == source_inputs(files)
    assert all(p in model['params'] for p in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'))
    runtime = source_inputs(['tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=300000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    assert MARKER in log and 'PASS rv32_program_tb' in log
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path
    outcomes = verify_trace(trace)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=sha(elf),
        trace_sha256=sha(trace), compile=compile_run, run=run, outcomes=outcomes))
    print(f'PASS {len(outcomes)} immediate HS/VS interrupt boundaries after CSR writes or SRET', flush=True)


if __name__ == '__main__':
    main()


"""Verify RV64 FENCE encodings drain write-through traffic before younger loads."""
import argparse
import json
import re

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/fence_order'
TOP = 'rv23_fence_order_tb'
FENCES = (0x0330000f, 0x8330000f, 0x0ff0000f, 0xf230830f)
MARKER = 'data=0x46454e43'
RUNTIME = ['tb/fixtures/bootrom/bootrom_host_jump64.hex',
           'sw/benchmarks/coremark/rv32_tim.ld']


def fixture():
    lines = ['.section .text.init,"ax"', '.option norvc', '.option norelax',
             '.globl _start', '_start:', 'la t0,fail', 'csrw mtvec,t0',
             'lui t0,0x80020', 'slli t0,t0,32', 'srli t0,t0,32',
             'li ra,23', 'li t1,42', 'li t2,99']
    for word in FENCES:
        lines += ['sd t1,0(t0)', f'.word 0x{word:08x}', 'ld t3,64(t0)',
                  'bne t3,t2,fail', 'bne t1,t3,1f', 'j fail', '1: addi t1,t1,1']
    lines += ['li t3,46', 'bne t1,t3,fail', 'li t3,23', 'bne ra,t3,fail',
              'lui t0,0x10000', 'li t1,0x46454e43', 'sw t1,0xc(t0)',
              'sw zero,0x14(t0)', 'halt: j halt',
              'fail: lui t0,0x10000', 'li t1,1', 'sw t1,0x14(t0)', 'j halt',
              '.section .data,"aw"', '.dword 0', '.zero 56', '.dword 99']
    return '\n'.join(lines) + '\n'


def verify(log):
    assert MARKER in log and '[host-finish code=0]' in log and 'PASS rv32_program_tb' in log
    events = [(int(cycle), event, int(value, 16))
              for cycle, event, value in re.findall(r'^FENCE_ORDER (\d+) (\w+) ([\da-f]+)$', log, re.M)]
    observed = [(cycle, event, value) for cycle, event, value in events if event != 'wait']
    expected = [(event, value) for word in FENCES for event, value in
                [('write_request', 0x80020000), ('write_response', 0x80020000),
                 ('retire', word), ('read_request', 0x80020040)]]
    assert [(event, value) for _, event, value in observed] == expected, observed
    coverage = []
    for index, word in enumerate(FENCES):
        start, response, retire, read = [cycle for cycle, _, _ in observed[index * 4:index * 4 + 4]]
        assert start < response < retire <= read, (start, response, retire, read)
        waits = [cycle for cycle, event, value in events if event == 'wait' and value == word]
        assert any(start <= cycle <= response for cycle in waits), (word, waits)
        coverage.append(dict(instruction=f'{word:08x}', write_request=start, write_response=response,
                             fence_retire=retire, read_request=read, drain_wait_cycles=len(waits)))
    return coverage


def check(record, inputs):
    assert record['passed'] and record['driver_sha256'] == sha(__file__)
    assert record['model']['inputs'] == inputs and record['model']['top'] == TOP
    assert record['runtime_inputs'] == source_inputs(RUNTIME)
    for name, digest in record['artifact_hashes'].items():
        assert sha(ROOT / name) == digest, name
    model = record['model']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    for run in (model['compile'], model['build'], record['compile'], record['run']):
        assert run['passed'] and run['exit_code'] == 0 and sha(ROOT / run['log']) == run['log_sha256']
    assert record['coverage'] == verify((ROOT / record['run']['log']).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify saved evidence')
    args = parser.parse_args()
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        'tb/rv32_program_tb.sv', f'tb/{TOP}.sv', 'tb/e2e/dpi/elf_loader.cpp']
    inputs = source_inputs(files)
    report = FOLDER / 'report.json'
    if args.check:
        record = json.loads(report.read_text(encoding='utf-8'))
    else:
        FOLDER.mkdir(parents=True, exist_ok=True)
        source, elf = FOLDER / 'test.S', FOLDER / 'test.elf'
        source.write_text(fixture(), encoding='utf-8')
        runtime = source_inputs(RUNTIME)
        with Simulator() as sim:
            compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh',
                '-mabi=lp64d', '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
                '-T', RUNTIME[1], source, '-o', elf], FOLDER / 'compile.log', 60)
            model = sim.build('rv23_fence_order', TOP, files)
            run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
                '+quiet_commit', '+timeout_cycles=100000', '+expected_exit_code=0'],
                FOLDER / 'simulation.log', 120)
        record = dict(passed=True, driver_sha256=sha(__file__), model=model,
                      runtime_inputs=runtime, compile=compile_run, run=run, coverage=verify(log),
                      artifact_hashes={path.relative_to(ROOT).as_posix(): sha(path)
                                       for path in (source, elf)})
        check(record, inputs)
        dump(report, record)
    check(record, inputs)
    print('PASS RV64 FENCE encodings: SRAM write response precedes fence retirement and younger load')


if __name__ == '__main__':
    main()

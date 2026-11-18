"""Verify RV64 FENCE, atomic and cache-block ordering on the running SoC."""
import argparse
import json
import re

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/fence_order'
TOP = 'rv23_fence_order_tb'
FENCES = (0x0330000f, 0x8330000f, 0x0ff0000f, 0xf230830f)
SRAM_WRITE = ('write', 0x80020000)
SRAM_READ = ('read', 0x80020040)
CLINT_WRITE = ('write', 0x02000000)
CLINT_READ = ('read', 0x02000000)
ATOMIC_ADDR = 0x80020080
ZERO_BLOCK = 0x80020100
CBO_ZERO = 0x004a200f
VECTOR_LOAD = 0x020af407
IO_CASES = (
    (0x0140000f, SRAM_WRITE, CLINT_WRITE, 'sd t1,0(t0)', 'sw t4,0(s0)', []),
    (0x0820000f, CLINT_READ, SRAM_READ, 'lw t5,0(s0)', 'ld t3,64(t0)', ['bne t5,t4,fail', 'bne t3,t2,fail']),
    (0x0420000f, CLINT_WRITE, SRAM_READ, 'sw zero,0(s0)', 'ld t3,64(t0)', ['bne t3,t2,fail']),
    (0x0180000f, SRAM_WRITE, CLINT_READ, 'sd t1,0(t0)', 'lw t5,0(s0)', ['bnez t5,fail']),
    (0x0240000f, SRAM_READ, CLINT_WRITE, 'ld t3,64(t0)', 'sw t4,0(s0)', ['bne t3,t2,fail']),
    (0x0810000f, CLINT_READ, SRAM_WRITE, 'lw t5,0(s0)', 'sd t1,0(t0)', ['bne t5,t4,fail']),
)
ATOMIC_CASES = (
    (0x01393f2f, 'amoadd.d t5,s3,(s2)', 100),
    (0x05393f2f, 'amoadd.d.aq t5,s3,(s2)', 101),
    (0x03393f2f, 'amoadd.d.rl t5,s3,(s2)', 102),
    (0x07393f2f, 'amoadd.d.aqrl t5,s3,(s2)', 103),
    (0x14093f2f, 'lr.d.aq t5,(s2)', 104),
    (0x1b393f2f, 'sc.d.rl t5,s3,(s2)', 0),
)
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
              'lui s0,0x02000', 'li t4,1']
    for word, _, _, first, second, checks in IO_CASES:
        lines += [first, f'.word 0x{word:08x}', second, *checks]
    lines += ['li s2,0x80020080', 'li s3,1']
    for _, instruction, expected in ATOMIC_CASES:
        lines += ['sd t1,0(t0)', instruction, 'ld t3,64(t0)',
                  f'li t4,{expected}', 'bne t5,t4,fail', 'bne t3,t2,fail']
    lines += ['ld t3,0(s2)', 'bne t3,s3,fail',
              'li s5,0x80020100', 'addi s4,s5,13', 'li t3,-1',
              'sd t3,-8(s5)', 'sd t3,64(s5)']
    lines += [f'sd t3,{offset}(s5)' for offset in range(0, 64, 8)]
    lines += ['ld t4,0(s5)', 'bne t4,t3,fail', 'li t4,0x600', 'csrs mstatus,t4',
              'vsetivli zero,8,e64,m4,tu,mu', f'.word 0x{CBO_ZERO:08x}', 'fence rw,rw',
              'vle64.v v8,(s5)', 'vmv.x.s t4,v8', 'li t2,0x13579bdf2468ace0',
              'bne t4,t2,fail', 'vmseq.vi v0,v8,0', 'vcpop.m t4,v0', 'li t2,7',
              'bne t4,t2,fail', 'ld t4,0(s5)', 'li t2,0x13579bdf2468ace0', 'bne t4,t2,fail',
              'ld t4,-8(s5)', 'bne t4,t3,fail', 'ld t4,64(s5)', 'bne t4,t3,fail']
    lines += ['lui t0,0x10000', 'li t1,0x46454e43', 'sw t1,0xc(t0)',
              'sw zero,0x14(t0)', 'halt: j halt',
              'fail: lui t0,0x10000', 'li t1,1', 'sw t1,0x14(t0)', 'j halt',
              '.section .data,"aw"', '.dword 0', '.zero 56', '.dword 99', '.zero 56', '.dword 100']
    return '\n'.join(lines) + '\n'


def verify(log):
    assert MARKER in log and '[host-finish code=0]' in log and 'PASS rv32_program_tb' in log
    events = [(int(cycle), event, int(value, 16))
              for cycle, event, value in re.findall(r'^FENCE_ORDER (\d+) (\w+) ([\da-f]+)$', log, re.M)]
    observed = [(cycle, event, value) for cycle, event, value in events if event != 'wait']
    cases = [(word, SRAM_WRITE, SRAM_READ) for word in FENCES]
    cases += [(word, predecessor, successor) for word, predecessor, successor, *_ in IO_CASES]
    expected = []
    for word, (pred, pred_addr), (succ, succ_addr) in cases:
        expected.extend([(pred + '_request', pred_addr), (pred + '_response', pred_addr), ('retire', word),
                         (succ + '_request', succ_addr), (succ + '_response', succ_addr)])
    for word, _, _ in ATOMIC_CASES:
        expected.extend([('write_request', SRAM_WRITE[1]), ('write_response', SRAM_WRITE[1]),
                         ('atomic_request', ATOMIC_ADDR), ('atomic_response', ATOMIC_ADDR),
                         ('atomic_retire', word), ('read_request', SRAM_READ[1]), ('read_response', SRAM_READ[1])])
    assert [(event, value) for _, event, value in observed[:len(expected)]] == expected, observed
    coverage = []
    for index, (word, predecessor, successor) in enumerate(cases):
        start, response, retire, request, completed = [cycle for cycle, _, _ in observed[index * 5:index * 5 + 5]]
        assert start < response < retire <= request < completed, (start, response, retire, request, completed)
        waits = [cycle for cycle, event, value in events if event == 'wait' and value == word]
        if word in FENCES:
            assert any(start <= cycle <= response for cycle in waits), (word, waits)
        coverage.append(dict(instruction=f'{word:08x}', predecessor=list(predecessor), successor=list(successor),
                             predecessor_request=start, predecessor_response=response, fence_retire=retire,
                             successor_request=request, successor_response=completed, drain_wait_cycles=len(waits)))
    atomics = []
    atomic_events = observed[5 * len(cases):len(expected)]
    for index, (word, _, _) in enumerate(ATOMIC_CASES):
        start, response, memory_request, memory_response, retire, request, completed = (
            cycle for cycle, _, _ in atomic_events[7 * index:7 * index + 7])
        assert start < response < memory_request < memory_response < retire <= request < completed
        atomics.append(dict(instruction=f'{word:08x}', write_response=response, atomic_request=memory_request,
                            atomic_response=memory_response, atomic_retire=retire, read_request=request))
    zero_events = observed[len(expected):]
    zero_beats = [(cycle, value) for cycle, event, value in zero_events if event == 'zero_beat']
    debug_writes = [(cycle, value) for cycle, event, value in zero_events if event == 'debug_write']
    vector_reads = [(cycle, value) for cycle, event, value in zero_events if event == 'vector_read']
    control = [(cycle, event, value) for cycle, event, value in zero_events
               if event not in ('zero_beat', 'debug_write', 'vector_read')]
    block_words = list(range(ZERO_BLOCK, ZERO_BLOCK + 64, 8))
    assert [value for _, value in zero_beats] == block_words, zero_events
    assert [value for _, value in vector_reads] == block_words, zero_events
    assert len(debug_writes) == 1 and debug_writes[0][1] == ZERO_BLOCK, zero_events
    assert [(event, value) for _, event, value in control] == [
        ('block_retire', CBO_ZERO), ('retire', FENCES[0]), ('block_retire', VECTOR_LOAD)]
    first, last = zero_beats[0][0], zero_beats[-1][0]
    debug_cycle = debug_writes[0][0]
    zero_retire, fence_retire, vector_retire = [cycle for cycle, _, _ in control]
    assert first < debug_cycle < last < zero_retire < fence_retire <= vector_reads[0][0], zero_events
    assert vector_reads[-1][0] < vector_retire, zero_events
    return dict(fences=coverage, atomics=atomics,
                block_zero=dict(zero_writes=len(zero_beats), vector_reads=len(vector_reads),
                                first_cycle=first, last_cycle=last, debug_cycle=debug_cycle,
                                zero_retire=zero_retire, fence_retire=fence_retire,
                                vector_retire=vector_retire))


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
    print('PASS RV64 ordering: ten FENCE, six atomics and concurrent CBO.ZERO', record['coverage']['block_zero'])


if __name__ == '__main__':
    main()

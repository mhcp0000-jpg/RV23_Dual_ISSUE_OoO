"""Exercise the Svpbmt alias-switching sequences on scalar and vector memory."""

import json
import re
from itertools import permutations

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, Simulator, dump, sha


FOLDER = 'out/rva23/svpbmt_alias_order'
PA = 0x80090000
VIRTUAL = (0x40003000, 0x40004000, 0x40005000)
CASES = [(source, target, vector_store) for source, target in permutations(range(3), 2)
         for vector_store in (False, True)]
ZERO_STRIDE_OFFSET = 64 * len(CASES)
ZERO_STRIDE_LOAD = PA + ZERO_STRIDE_OFFSET
ZERO_STRIDE_STORE = ZERO_STRIDE_LOAD + 8
FENCE = 0x0ff0000f
CBO_FLUSH = 0x0025200f  # cbo.flush (a0)


def fixture():
    lines = [
        '.section .text.init,"ax"', '.option norvc', '.option norelax', '.globl _start',
        '_start:', 'la t0,fail', 'csrw mtvec,t0', 'csrw stvec,t0',
        'li t0,-1', 'csrw pmpaddr0,t0', 'li t0,31', 'csrw pmpcfg0,t0',
        'li t0,0x4000000000000040', 'csrw menvcfg,t0',
        'la t0,root', 'li t1,0x200000cf', 'sd t1,16(t0)',
    ]
    for table, next_table, offset in [('root', 'mid', 8), ('mid', 'leaf', 0)]:
        lines += [f'la t0,{table}', f'la t1,{next_table}', 'srli t1,t1,2', 'ori t1,t1,1',
                  f'sd t1,{offset}(t0)']
    lines.append('la t0,leaf')
    for attribute in range(3):
        pte = (PA >> 2) | 0xc7 | (attribute << 61)
        lines += [f'li t1,{pte:#x}', f'sd t1,{(attribute + 3) * 8}(t0)']
    lines += ['la t0,root', 'srli t0,t0,12', 'li t1,0x8000000000000000', 'or t0,t0,t1',
              'csrw satp,t0', 'sfence.vma', 'la t0,supervisor', 'csrw mepc,t0',
              'li t0,0xa00', 'csrw mstatus,t0', 'mret', 'supervisor:',
              'vsetivli zero,2,e64,m1,tu,mu']
    for index, (source, target, vector_store) in enumerate(CASES):
        offset = 64 * index
        value = 0x1234567800000000 | index
        lines += [f'li s0,{VIRTUAL[source] + offset:#x}', f'li s1,{VIRTUAL[target] + offset:#x}',
                  'ld t6,0(s0)', f'li s2,{value:#x}', 'addi s3,s2,1']
        if vector_store:
            lines += ['vmv.v.x v8,s2', 'vslide1down.vx v9,v8,s3', 'vse64.v v9,(s0)']
        else:
            lines += ['sd s2,0(s0)', 'sd s3,8(s0)']
        lines.append('fence iorw,iorw')
        if 0 in (source, target):
            # Zicbom uses the physical block even through a non-cacheable alias.
            lines += [f'li a0,{VIRTUAL[max(source, target)] + offset:#x}',
                      '.word 0x0025200f', 'fence iorw,iorw']
        if vector_store:
            lines += ['ld a0,0(s1)', 'bne a0,s2,fail', 'ld a0,8(s1)', 'bne a0,s3,fail']
        else:
            lines += ['vle64.v v8,(s1)', 'vmv.x.s a0,v8', 'bne a0,s2,fail',
                      'vslidedown.vi v9,v8,1', 'vmv.x.s a0,v9', 'bne a0,s3,fail']
        if source == 0:
            lines += ['fence iorw,iorw', 'mv a0,s1', '.word 0x0025200f', 'fence iorw,iorw',
                      'ld a0,0(s0)', 'bne a0,s2,fail']
    lines += [
        # PBMT=IO makes each active element request observable on AXI.
        f'li s0,{VIRTUAL[2] + ZERO_STRIDE_OFFSET:#x}', 'addi s1,s0,8',
        'li s2,21', 'sd s2,0(s0)', 'sd zero,0(s1)', 'fence iorw,iorw',
        'vsetivli zero,4,e64,m2,tu,mu', 'li t2,0', 'vlse64.v v8,(s0),t2',
        'vmseq.vx v16,v8,s2', 'vcpop.m a0,v16', 'li t0,4', 'bne a0,t0,fail',
        'li t0,5', 'vmv.s.x v0,t0', 'li s2,27', 'vmv.v.x v8,s2',
        'vsse64.v v8,(s1),t2,v0.t', 'fence iorw,iorw',
        'ld a0,0(s1)', 'bne a0,s2,fail',
        'li t1,1', 'j finish', 'fail:', 'li t1,3', 'finish:', 'la t0,tohost',
        'sd t1,0(t0)', 'halt: j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0', '.section .bss', '.balign 4096',
        'root:.space 4096', 'mid:.space 4096', 'leaf:.space 4096',
    ]
    return '\n'.join(lines) + '\n'


def verify_traces(sail_trace, rtl_trace):
    rtl = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), rtl)
    assert mismatch is None, mismatch
    observed = []
    for row in rtl:
        if int(row['pc'], 16) < 0x80000000:
            continue
        assert row['trap'] == '0', row
        word = int(row['instruction'], 16)
        if word in (FENCE, CBO_FLUSH):
            observed.append(word)
    expected = []
    for source, target, _ in CASES:
        expected.append(FENCE)
        if 0 in (source, target):
            expected.extend((CBO_FLUSH, FENCE))
        if source == 0:
            expected.extend((FENCE, CBO_FLUSH, FENCE))
    expected.extend((FENCE, FENCE))
    assert observed == expected
    return dict(access_pairs=len(CASES), cached_round_trips=sum(source == 0 for source, _, _ in CASES),
                flushes=observed.count(CBO_FLUSH), matched_events=events)


def verify_bus(log):
    reads = [[] for _ in CASES]
    zero_stride_reads = []
    pattern = r'^BUSDBG .* AR=1/1 .*?addr=([\da-f]+) len=([\da-f]+) .*?cache=([\da-f]+) '
    for address_text, length, cache in re.findall(pattern, log, re.M):
        address = int(address_text, 16)
        if PA <= address < PA + 64 * len(CASES):
            assert int(length, 16) == 0
            reads[(address - PA) // 64].append((address, int(cache, 16)))
        elif address in (ZERO_STRIDE_LOAD, ZERO_STRIDE_STORE):
            zero_stride_reads.append((address, int(length, 16), int(cache, 16)))
    cache_line_refills = uncached_reads = pma_vector_reads = 0
    for index, (source, target, vector_store) in enumerate(CASES):
        line = PA + 64 * index
        line_fill = [(line + offset, 3) for offset in range(0, 64, 8)]
        expected = line_fill.copy() if source == 0 else [(line, 0)]
        if target == 0 and vector_store:
            expected += line_fill
        else:
            # The vector memory head issues element reads on its own AXI path.
            attribute = 3 if target == 0 else 0
            expected += [(line, attribute), (line + 8, attribute)]
        if source == 0:
            expected += line_fill
        assert reads[index] == expected, (index, reads[index], expected)
        cache_line_refills += sum(cache == 3 for _, cache in reads[index]) // 8
        uncached_reads += sum(cache == 0 for _, cache in reads[index])
        pma_vector_reads += 2 if target == 0 and not vector_store else 0
    assert zero_stride_reads == [(ZERO_STRIDE_LOAD, 0, 0)] * 4 + [(ZERO_STRIDE_STORE, 0, 0)]
    zero_stride_writes = []
    for address_text in re.findall(r'^BUSDBG .* AW=1/1 addr=([\da-f]+)$', log, re.M):
        address = int(address_text, 16)
        if address in (ZERO_STRIDE_LOAD, ZERO_STRIDE_STORE):
            zero_stride_writes.append(address)
    # The first two writes are scalar setup. Mask=0101 enables two vector stores.
    assert zero_stride_writes == [ZERO_STRIDE_LOAD, ZERO_STRIDE_STORE] + [ZERO_STRIDE_STORE] * 2
    assert 'PASS rv32_program_tb' in log
    return dict(cache_line_refills=cache_line_refills, uncached_reads=uncached_reads,
                pma_vector_reads=pma_vector_reads, zero_stride_vector_reads=4,
                zero_stride_masked_vector_writes=2)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'test.S'
    source.write_text(fixture(), encoding='utf-8')
    results = run_fixture(source, folder, __file__, verify_traces)
    report_path = folder / 'report.json'
    report = json.loads(report_path.read_bytes())
    report['passed'] = False
    dump(report_path, report)
    model, elf = report['model'], folder / 'test.elf'
    assert sha(elf) == report['elf_sha256']
    with Simulator() as sim:
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            '+quiet_commit', '+htif', '+bus_debug', '+timeout_cycles=100000', '+expected_exit_code=0'],
            folder / 'bus.log', 120)
    assert sha(elf) == report['elf_sha256'] and sha(ROOT / model['binary']) == model['binary_sha256']
    bus = verify_bus(log)
    report.update(passed=True, bus_run=run, bus=bus)
    dump(report_path, report)
    print('PASS Svpbmt attribute aliases', results, bus, flush=True)


if __name__ == '__main__':
    main()

"""Exercise all Sv39x4 root quadrants and the 41-bit GPA boundary."""

import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/sv39x4_root'
BASE = 'sw/tests/rv64_hypervisor_gstage.S'
MARKER = 'data=0x47504134'
PROBES = [(0x200a0018 | (quadrant << 39), 0x800a0018 + quadrant * 0x1000)
          for quadrant in range(4)]
PROBES.append(((1 << 41) - 8, 0x800a4ff8))
OUT_OF_RANGE = 1 << 41
REMAPS = [(index, (index + 1) % 4) for index in range(4)]
VS_GVA = 0x400a0018
VS_GPA_INDICES = (0, 1)
TEST_VALUE = 0x1234567880000000


def fixture():
    original = (ROOT / BASE).read_text(encoding='utf-8')
    setup, _ = original.split('hs_entry:\n', 1)
    lines = [setup, 'hs_entry:', 'csrw vsatp,zero', 'li t0,0x100', 'csrw hstatus,t0']
    for index, (gpa, pa) in enumerate(PROBES):
        root_offset = ((gpa >> 30) & 0x7ff) * 8
        level1_offset = ((gpa >> 21) & 0x1ff) * 8
        level0_offset = ((gpa >> 12) & 0x1ff) * 8
        lines += [
            'la t0,groot', f'li t1,{root_offset}', 'add t0,t0,t1',
            f'la t1,root_l1_{index}', 'srli t1,t1,2', 'ori t1,t1,1', 'sd t1,0(t0)',
            f'la t0,root_l1_{index}', f'li t1,{level1_offset}', 'add t0,t0,t1',
            f'la t1,root_l0_{index}', 'srli t1,t1,2', 'ori t1,t1,1', 'sd t1,0(t0)',
            f'la t0,root_l0_{index}', f'li t1,{level0_offset}', 'add t0,t0,t1',
            f'li t1,{((pa & ~0xfff) >> 2) | 0xd7:#x}', 'sd t1,0(t0)',
            f'li t0,{pa:#x}', f'li t1,{(TEST_VALUE + index):#x}', 'sd t1,0(t0)',
        ]
    lines += ['hfence.gvma', 'hfence.vvma']
    for index, (gpa, pa) in enumerate(PROBES):
        lines += [
            f'li s0,{index + 1}', f'li t0,{gpa:#x}', 'hlv.d t1,(t0)',
            f'li t2,{(TEST_VALUE + index):#x}', 'bne t1,t2,fail',
            'not t2,t2', 'hsv.d t2,(t0)', f'li t0,{pa:#x}', 'ld t1,0(t0)', 'bne t1,t2,fail',
        ]
    for index, replacement in REMAPS:
        gpa = PROBES[index][0]
        pa = PROBES[replacement][1]
        pte_offset = ((gpa >> 12) & 0x1ff) * 8
        lines += [
            f'li s0,{7 + index}', f'la t0,root_l0_{index}', f'li t1,{pte_offset}', 'add t0,t0,t1',
            f'li t1,{((pa & ~0xfff) >> 2) | 0xd7:#x}', 'sd t1,0(t0)',
            f'li t3,{gpa >> 2:#x}', 'sfence.w.inval', 'hinval.gvma t3,zero', 'sfence.inval.ir',
            f'li t0,{gpa:#x}', 'hlv.d t1,(t0)',
            f'li t2,{(~(TEST_VALUE + replacement) & 0xffffffffffffffff):#x}', 'bne t1,t2,fail',
        ]
    # The first G root quadrant also translates the VS page-table pages.
    vs_pte_offset = ((VS_GVA >> 12) & 0x1ff) * 8
    lines += [
        'li s0,11', 'la t0,root_l1_0', 'la t1,gvsptes', 'srli t1,t1,2',
        'ori t1,t1,1', 'sd t1,1024(t0)',
        'la t0,gvsptes', 'la t1,vslevel0', 'srli t1,t1,2', 'ori t1,t1,0x53', 'sd t1,16(t0)',
        'la t0,vslevel1', 'li t1,0x4000801', 'sd t1,0(t0)',  # GPA 0x10002000
        'la s4,vslevel0', f'li t1,{vs_pte_offset}', 'add s4,s4,t1',
    ]
    for step, index in enumerate(VS_GPA_INDICES):
        pte = ((PROBES[index][0] & ~0xfff) >> 2) | 0xc7
        lines += [f'li s0,{11 + step}', f'li t1,{pte:#x}', 'sd t1,0(s4)']
        if step == 0:
            lines += ['li t0,0x8000000000010000', 'csrw vsatp,t0', 'hfence.gvma', 'hfence.vvma']
        else:
            lines += [f'li t3,{VS_GVA:#x}', 'sfence.w.inval', 'hinval.vvma t3,zero', 'sfence.inval.ir']
        pa_index = REMAPS[index][1]
        lines += [f'li t0,{VS_GVA:#x}', 'hlv.d t1,(t0)',
                  f'li t2,{(~(TEST_VALUE + pa_index) & 0xffffffffffffffff):#x}', 'bne t1,t2,fail']
    lines += [
        'csrw vsatp,zero', 'hfence.vvma',
        'li s0,6', f'li s1,{OUT_OF_RANGE:#x}', 'la s2,fault_probe', 'li s3,0',
        'fault_probe:', 'hlv.d t1,(s1)', 'li t0,1', 'bne s3,t0,fail',
        'lui t0,0x10000', 'li t1,0x47504134', 'sw t1,0xc(t0)',
        'sw zero,0x14(t0)', 'halt: j halt',
        'hs_trap:', 'li t0,6', 'bne s0,t0,fail', 'bnez s3,fail',
        'csrr t0,scause', 'li t1,21', 'bne t0,t1,fail', 'csrr t0,sepc', 'bne t0,s2,fail',
        'csrr t1,stval', 'bne t1,s1,fail', 'csrr t1,hstatus', 'andi t1,t1,0x40',
        'beqz t1,fail', 'li s3,1', 'addi t0,t0,4', 'csrw sepc,t0', 'sret',
        'fail:', 'lui t0,0x10000', 'sw s0,0xc(t0)', 'li t1,1', 'sw t1,0x14(t0)', 'j halt',
        original[original.index('.section .bss'):],
        '.balign 4096', 'vslevel0:.skip 4096',
    ]
    for index in range(len(PROBES)):
        lines += [f'root_l1_{index}:.skip 4096', f'root_l0_{index}:.skip 4096']
    return '\n'.join(lines) + '\n'


def verify_trace(path):
    with path.open(newline='') as stream:
        rows = [row for row in csv.DictReader(stream) if int(row['pc'], 16) >= 0x80000000]
    reads = [row for row in rows if int(row['instruction'], 16) == 0x6c02c373]
    expected_reads = [TEST_VALUE + index for index in range(len(PROBES))]
    remapped = [~(TEST_VALUE + replacement) & 0xffffffffffffffff for _, replacement in REMAPS]
    expected_reads.extend(remapped)
    expected_reads.extend(remapped[index] for index in VS_GPA_INDICES)
    assert [int(row['wdata'], 16) for row in reads] == expected_reads
    write_inval, g_inval, vs_inval, read_inval, hlv_d = 0x18000073, 0x660e0073, 0x260e0073, 0x18100073, 0x6c02c373
    expected_order = ([hlv_d] * len(PROBES) + [write_inval, g_inval, read_inval, hlv_d] * len(REMAPS)
                      + [hlv_d, write_inval, vs_inval, read_inval, hlv_d])
    events = set(expected_order)
    observed = [int(row['instruction'], 16) for row in rows if int(row['instruction'], 16) in events]
    assert observed == expected_order, observed
    writes = [row for row in rows if (int(row['instruction'], 16) & 0xfe007fff) == 0x6e004073]
    assert len(writes) == len(PROBES) and all(row['trap'] == '0' for row in writes)
    traps = [row for row in rows if row['trap'] == '1']
    assert len(traps) == 1 and int(traps[0]['cause']) == 21
    assert int(traps[0]['tval'], 16) == OUT_OF_RANGE
    return traps


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
    assert all(p in model['params'] for p in ('-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1', '-GHAS_MMU=1'))
    runtime = source_inputs([BASE, 'tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh_svinval', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
            '+timeout_cycles=300000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
    assert MARKER in log and 'PASS rv32_program_tb' in log
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path
    traps = verify_trace(trace)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        generator_sha256=sha(__file__), source_sha256=sha(source), elf_sha256=sha(elf),
        trace_sha256=sha(trace), compile=compile_run, run=run, probes=PROBES, remaps=REMAPS,
        vs_remap={'gva': VS_GVA, 'gpas': [PROBES[index][0] for index in VS_GPA_INDICES]}, traps=traps))
    print('PASS Sv39x4 root, 41-bit boundary, and G-stage and VS-stage HINVAL remaps', flush=True)


if __name__ == '__main__':
    main()


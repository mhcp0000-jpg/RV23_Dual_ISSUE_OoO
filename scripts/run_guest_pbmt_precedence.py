"""Check Svpbmt precedence through native misaligned HLV.D accesses."""

import csv
import itertools
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/guest_pbmt_precedence'
BASE = 'sw/tests/rv64_hypervisor_gstage.S'
CONTROL = 'out/negative_controls/svpbmt_stage_precedence'
MMU_PATH = 'rtl/soc/rv23_mmu.sv'
ADDRESS = 0x400a0001
MARKER = 'data=0x50424d54'
PAIRS = list(itertools.product(range(3), repeat=2))


def fixture():
    original = (ROOT / BASE).read_text(encoding='utf-8')
    setup, _ = original.split('hs_entry:\n', 1)
    setup += """hs_entry:
  li t0,0x100
  csrw hstatus,t0
  li t0,0x4000000000000000
  csrw henvcfg,t0
  li t0,0x800a0000
  li t1,0x7766554433221100
  sd t1,0(t0)
  li t1,0xffeeddccbbaa9988
  sd t1,8(t0)
  li s4,0x400a0001
"""
    lines = [setup]
    for index, (vs_type, g_type) in enumerate(PAIRS, 1):
        lines += [
            f'li s0,{index}', f'li s1,{5 if (vs_type or g_type) == 2 else 0}',
            'li s3,0', 'la t0,vslevel1', f'li t1,{(vs_type << 61) | (0x20000000 >> 2) | 0xcf:#x}',
            'sd t1,0(t0)', 'la t0,glevel1', 'li t1,2048', 'add t0,t0,t1',
            f'li t1,{(g_type << 61) | (0x80000000 >> 2) | 0xdf:#x}', 'sd t1,0(t0)',
            'hfence.gvma', 'hfence.vvma', f'la s2,probe_{index}',
            f'probe_{index}:', 'hlv.d t0,(s4)', 'bne s1,s3,fail',
        ]
        if (vs_type or g_type) != 2:
            lines += ['li t1,0x8877665544332211', 'bne t0,t1,fail']
    lines += [
        'lui t0,0x10000', 'li t1,0x50424d54', 'sw t1,0xc(t0)',
        'sw zero,0x14(t0)', 'halt: j halt',
        'hs_trap:', 'csrr s3,scause', 'bne s1,s3,fail', 'beqz s1,fail',
        'csrr t0,sepc', 'bne t0,s2,fail', 'csrr t1,stval', 'bne t1,s4,fail',
        'csrr t1,htval', 'bnez t1,fail', 'addi t0,t0,4', 'csrw sepc,t0', 'sret',
        'fail:', 'lui t0,0x10000', 'sw s0,0xc(t0)', 'li t1,1', 'sw t1,0x14(t0)', 'j halt',
        original[original.index('.section .bss'):],
    ]
    return '\n'.join(lines)


def verify_trace(path, *, pre_fix=False):
    with path.open(newline='') as stream:
        records = [row for row in csv.DictReader(stream) if int(row['pc'], 16) >= 0x80000000]
    # HLV.D t0,(s4) has its rs1 in x20 and destination in x5.
    probes = [row for row in records if int(row['instruction'], 16) == 0x6c0a42f3]
    expected = [0, 0, 5, 0, 0, 5] if pre_fix else [5 if (vs or g) == 2 else 0 for vs, g in PAIRS]
    assert len(probes) == len(expected), len(probes)
    assert [int(row['cause']) if row['trap'] == '1' else 0 for row in probes] == expected, probes
    assert [row for row in records if row['trap'] == '1'] == [row for row in probes if row['trap'] == '1']
    for row, cause in zip(probes, expected):
        if cause:
            assert int(row['tval'], 16) == ADDRESS, row
        else:
            assert row['gpr_we'] == '1' and int(row['wdata'], 16) == 0x8877665544332211, row
    return expected


def control_inputs(model):
    inputs = dict(model['inputs'])
    replacement = inputs.pop(MMU_PATH, None)
    if replacement is None:
        inputs[MMU_PATH] = inputs.pop(f'{CONTROL}/rv23_mmu.sv')
    else:
        inputs[MMU_PATH] = replacement
    return inputs


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source, elf, trace = (folder / name for name in ('test.S', 'test.elf', 'commit.csv'))
    source.write_text(fixture(), encoding='utf-8')
    model = json.loads((ROOT / 'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    previous = json.loads((ROOT / CONTROL / 'prefixed_model.json').read_text(encoding='utf-8'))
    previous_rtl = ROOT / CONTROL / 'rv23_mmu.sv'
    assert previous['params'] == model['params'] and previous['inputs'].keys() == model['inputs'].keys()
    assert sha(previous_rtl) == previous['inputs'][MMU_PATH]
    runtime = source_inputs([BASE, 'tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path
    old_trace = ROOT / CONTROL / 'native_commit.csv'
    with Simulator() as sim:
        changed = {p for p in model['inputs'] if previous['inputs'][p] != model['inputs'][p]}
        if changed == {MMU_PATH}:
            previous_binary = ROOT / CONTROL / 'Vrv32_program_tb.exe'
        else:
            files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
                'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
                'tb/rv32_program_tb.sv', 'tb/e2e/dpi/elf_loader.cpp']
            files[files.index(MMU_PATH)] = f'{CONTROL}/rv23_mmu.sv'
            previous = sim.build('rva23_pbmt_pre_fix', model['top'], files, model['params'])
            previous_binary = ROOT / previous['binary']
        prior_inputs = control_inputs(previous)
        assert prior_inputs.keys() == model['inputs'].keys()
        assert {p for p in prior_inputs if prior_inputs[p] != model['inputs'][p]} == {MMU_PATH}
        assert sha(previous_binary) == previous['binary_sha256']
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
        elf_hash = sha(elf)

        def simulate(binary, commit_path, log_path, expected_exit):
            return sim.run([binary, f'+elf={elf.relative_to(ROOT).as_posix()}',
                f'+trace_file={commit_path.relative_to(ROOT).as_posix()}', '+quiet_commit',
                '+timeout_cycles=300000', f'+expected_exit_code={expected_exit}'], log_path, 120)

        run, log = simulate(ROOT / model['binary'], trace, folder / 'simulation.log', 0)
        old_run, old_log = simulate(previous_binary, old_trace, ROOT / CONTROL / 'native_simulation.log', 1)
    assert 'PASS rv32_program_tb' in log and MARKER in log and '[host-finish code=0]' in log
    assert 'data=0x00000006' in old_log and '[host-finish code=1]' in old_log
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest, path
    assert sha(elf) == elf_hash
    outcomes = verify_trace(trace)
    before = verify_trace(old_trace, pre_fix=True)
    dump(folder / 'report.json', dict(passed=True, model=model, runtime_inputs=runtime,
        source_sha256=sha(source), generator_sha256=sha(__file__), elf_sha256=elf_hash,
        trace_sha256=sha(trace), compile=compile_run, run=run, outcomes=outcomes,
        pre_fix=dict(run=old_run, trace_sha256=sha(old_trace), model=previous, outcomes=before,
                     binary=previous_binary.relative_to(ROOT).as_posix())))
    print('PASS Svpbmt native stage precedence: 9 cases, 4 expected access faults, same-ELF pre-fix failure', flush=True)


if __name__ == '__main__':
    main()


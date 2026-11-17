"""Check VS/VU and MPRV word accesses across a two-stage page boundary."""

import argparse
import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/guest_misaligned'
BASE = 'sw/tests/rv64_hypervisor_vector_faults.S'
BODY = 'sw/tests/rv64_guest_misaligned_body.S'
MARKER = 'data=0x48535054'
MODES = ('VS', 'VU', 'MPRV-VS', 'MPRV-VU')


def fixture(mode):
    template = (ROOT / BASE).read_text(encoding='utf-8')
    setup = template.split('hs_entry:\n', 1)[0]
    vu = mode.endswith('VU')
    mprv = mode.startswith('MPRV-')
    flags = '0xdf' if vu else '0xcf'
    replacements = {
        '  li t0,0xcf\n': f'  li t0,{flags}\n',
        ('  li t0,(0x20000000 >> 2) | 0xcf\n'
         '  sd t0,0(t1)                  # guest 0x40000000 -> SRAM 0x80000000\n'): f'''  li t0,(0x10002000 >> 2) | 1
  sd t0,0(t1)
  la t1,vslevel0
  li t0,(0x20000000 >> 2) | {flags}
  li t2,256
init_vsdata:
  sd t0,0(t1)
  addi t1,t1,8
  addi t0,t0,1024
  addi t2,t2,-1
  bnez t2,init_vsdata
''',
        '  li t0,(0x800a4000 >> 2) | 0xdb\n': '  li t0,(0x800b4000 >> 2) | 0xdf\n',
        '  sd t0,1312(t1)            # G-stage W denied on the second data page\n':
            '  sd t0,1312(t1)            # Second page backs onto a different physical region\n',
        '  sd t0,8(t1)\n  la t0,groot\n': '''  sd t0,8(t1)
  la t0,vslevel0
  srli t0,t0,2
  ori t0,t0,0x53
  sd t0,16(t1)
  la t0,groot
''',
    }
    for before, after in replacements.items():
        assert setup.count(before) == 1, before
        setup = setup.replace(before, after)
    if mprv:
        assert setup.count('  mret\n') == 1
        setup = setup.replace('  mret\n', '  j hs_entry\n')
        pmp = '  csrw pmpaddr0,t0\n  li t0,31\n'
        assert setup.count(pmp) == 1
        setup = setup.replace(pmp, '  csrw pmpaddr1,t0\n  li t0,0x1f00\n')
    setup = '\n'.join(line.rstrip() for line in setup.splitlines()) + '\n'
    status = ('0x80', '0x2200', 8) if vu else ('0x180', '0x2300', 10)
    mode_absolutes = '\n'.join(f'.equ GUEST_{name}, {value}' for name, value in
                               zip(('HSTATUS', 'SSTATUS', 'ECALL'), status))
    mstatus = (1 << 39) | (1 << 17) | (0 if vu else 1 << 11)
    mode_absolutes += (f'\n#define GUEST_MPRV {int(mprv)}\n'
                       f'.equ GUEST_MSTATUS, {mstatus:#x}\n.equ GUEST_PTE_FLAGS, {flags}')
    tables = template[template.index('.section .bss'):]
    return '\n'.join((setup, mode_absolutes, (ROOT / BODY).read_text(encoding='utf-8'), tables,
                      '.balign 4096\nvslevel0: .skip 4096\n'))


def verify_trace(trace, mode):
    mprv = mode.startswith('MPRV-')
    base = 0x80000000 if mprv else 0x40000000
    with trace.open(newline='') as stream:
        guest = [row for row in csv.DictReader(stream) if base <= int(row['pc'], 16) < base + 0x20000]
    traps = [row for row in guest if row['trap'] == '1']
    ecall = 8 if mode.endswith('VU') else 10
    expected = [23, 21, 15, 13, 7, 5, 7, 5] if mprv else [ecall, 23, 21, ecall, 15, 13, ecall]
    assert [int(row['cause']) for row in traps] == expected, traps
    faults = [row for row in traps if int(row['cause']) != ecall]
    assert all(int(row['tval'], 16) == 0x400a4000 and row['rd_write'] == '0' for row in faults), faults
    loads = [int(row['wdata'], 16) for row in guest if row['trap'] == '0' and
             int(row['instruction'], 16) in (0x00042603, 0x00046683)]
    assert loads == [0xffffffffff001122, 0x89abcdef], loads
    return dict(loads=loads, faults=faults)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Audit saved RTL execution')
    args = parser.parse_args()
    model_path = ROOT / 'out/rva23/hypervisor_integration/model.json'
    model = json.loads(model_path.read_bytes())
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_MMU=1'} <= set(model['params'])
    runtime = source_inputs([BASE, BODY, 'tb/fixtures/bootrom/bootrom_host_jump64.hex',
                             'sw/benchmarks/coremark/rv32_tim.ld'])
    inputs = {**model['inputs'], **runtime, model['binary']: model['binary_sha256']}
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    report_path = ROOT / FOLDER / 'report.json'
    if args.check:
        report = json.loads(report_path.read_bytes())
        assert report['passed'] and report['generator_sha256'] == sha(__file__)
        assert report['model'] == model and report['runtime_inputs'] == runtime
        assert set(report['cases']) == set(MODES)
        for mode, case in report['cases'].items():
            folder = ROOT / FOLDER / mode.lower()
            assert (folder / 'test.S').read_text(encoding='utf-8') == fixture(mode)
            for artifact, key in (('test.S', 'source'), ('test.elf', 'elf'), ('commit.csv', 'trace')):
                assert sha(folder / artifact) == case[key + '_sha256']
            for phase in ('compile', 'run'):
                record = case[phase]
                assert record['passed'] and record['exit_code'] == 0
                assert sha(ROOT / record['log']) == record['log_sha256']
            log = (ROOT / case['run']['log']).read_text(encoding='utf-8')
            assert MARKER in log and 'PASS rv32_program_tb' in log
            assert verify_trace(folder / 'commit.csv', mode) == case['outcomes']
        print('PASS current VS, VU and MPRV misaligned page split evidence', flush=True)
        return
    cases = {}
    with Simulator() as sim:
        for mode in MODES:
            folder = ROOT / FOLDER / mode.lower()
            folder.mkdir(parents=True, exist_ok=True)
            source, elf, trace = (folder / name for name in ('test.S', 'test.elf', 'commit.csv'))
            source.write_text(fixture(mode), encoding='utf-8')
            compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
                '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
                '-T', 'sw/benchmarks/coremark/rv32_tim.ld', source, '-o', elf], folder / 'compile.log', 60)
            run, log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
                f'+trace_file={trace.relative_to(ROOT).as_posix()}', '+quiet_commit',
                '+timeout_cycles=300000', '+expected_exit_code=0'], folder / 'simulation.log', 120)
            assert MARKER in log and 'PASS rv32_program_tb' in log
            cases[mode] = dict(compile=compile_run, run=run, outcomes=verify_trace(trace, mode),
                               source_sha256=sha(source), elf_sha256=sha(elf), trace_sha256=sha(trace))
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    dump(report_path, dict(passed=True, model=model, runtime_inputs=runtime, cases=cases,
         generator_sha256=sha(__file__)))
    print('PASS VS, VU and MPRV misaligned page split: 16 translation faults and 8 PMP access faults', flush=True)


if __name__ == '__main__':
    main()

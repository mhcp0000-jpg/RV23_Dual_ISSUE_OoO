"""Compare implicit VS PTE-read permissions on native RV64 H/V RTL and Sail."""

import argparse
import json
from itertools import product

from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


FOLDER = 'out/rva23/guest_pte_mxr'
BASE = 'sw/tests/rv64_hypervisor_gstage.S'
DATA = 0x765432108123fe80
STORE = 0x0123456789abcdef
GVA = 0x400a0000
PTE_GPA = 0x10001000
OPERATIONS = ('hlv.d', 'hlvx.wu', 'hsv.d')


def fixture():
    original = (ROOT / BASE).read_text(encoding='utf-8')
    lines = [original.split('hs_entry:\n', 1)[0], 'hs_entry:',
             'li t0,0x100', 'csrw hstatus,t0', f'li s0,{GVA:#x}']
    cases = []
    # Only this G-stage leaf changes. Its D bit stays clear because the
    # implicit access to the VS level-1 PTE is a read even for HSV.
    for leaf, flags in (('R', 0x53), ('X', 0x59), ('X_without_A', 0x19)):
        lines += ['la t0,gvsptes', 'la t1,vslevel1', 'srli t1,t1,2',
                  f'ori t1,t1,{flags:#x}', 'sd t1,8(t0)', 'hfence.gvma']
        for (hs_mxr, vs_mxr), op in product(((1, 0), (0, 1), (0, 0), (1, 1)), OPERATIONS):
            store = op == 'hsv.d'
            allowed = leaf == 'R' or (leaf == 'X' and hs_mxr)
            cause = 0 if allowed else 23 if store else 21
            case = dict(leaf=leaf, hs_mxr=hs_mxr, vs_mxr=vs_mxr, operation=op, cause=cause)
            cases.append(case)
            lines += [f'li s7,{len(cases)}', 'li t0,0x80000', 'csrc sstatus,t0',
                      f'li t1,{vs_mxr << 19:#x}', 'csrw vsstatus,t1']
            if hs_mxr:
                lines += ['csrs sstatus,t0']
            # Force the PTE read in each case, including after a warmer
            # translation was obtained under different MXR settings.
            lines += ['hfence.gvma', 'hfence.vvma', 'li s8,0x800a0000', f'li t1,{DATA:#x}', 'sd t1,0(s8)',
                      f'li s1,{cause}', 'li s3,0', f'la s4,probe_{len(cases)}',
                      f'li a2,{STORE:#x}', f'probe_{len(cases)}:', f'{op} a2,(s0)',
                      'bne s3,s1,fail']
            load_result = DATA if op == 'hlv.d' else DATA & 0xffffffff
            expected_register = STORE if store or cause else load_result
            lines += [f'li t1,{expected_register:#x}', 'bne a2,t1,fail', 'ld t2,0(s8)',
                      f'li t1,{STORE if store and allowed else DATA:#x}', 'bne t2,t1,fail']
    lines += ['li t1,1', 'j finish', 'hs_trap:', 'beqz s1,fail',
              'csrr s3,scause', 'bne s3,s1,fail', 'csrr t0,sepc', 'bne t0,s4,fail',
              'csrr t1,stval', 'bne t1,s0,fail', 'csrr t1,htval',
              f'li t2,{PTE_GPA >> 2:#x}', 'bne t1,t2,fail',
              'csrr t1,htinst', 'li t2,0x3000', 'bne t1,t2,fail',
              'addi t0,t0,4', 'csrw sepc,t0', 'sret',
              'fail:', 'addi t1,s7,1', 'slli t1,t1,1', 'ori t1,t1,1',
              'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'stop: j stop',
              '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
              'tohost: .dword 0', 'fromhost: .dword 0', original[original.index('.section .bss'):]]
    return '\n'.join(lines) + '\n', cases


def trace_evidence(sail_csv, rtl_csv, cases):
    reference, rtl = read_csv(sail_csv), read_csv(rtl_csv)
    events, mismatch = compare(reference, rtl)
    assert mismatch is None, mismatch
    traps = [row for row in rtl if row['trap'] == '1' and int(row['pc'], 16) >= 0x80000000]
    assert [int(row['cause']) for row in traps] == [case['cause'] for case in cases if case['cause']]
    assert all(int(row['tval'], 16) == GVA and row['rd_write'] == '0' for row in traps), traps
    return events, traps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    code, cases = fixture()
    report_path = folder / 'report.json'
    source, elf, sail_csv, rtl_csv = (folder / name for name in ('test.S', 'test.elf', 'sail.csv', 'commit.csv'))
    model_path = ROOT / 'out/rva23/hypervisor_integration/model.json'
    reference_path = ROOT / 'out/reference/sail-event-driver/report.json'
    model = json.loads(model_path.read_bytes())
    reference = json.loads(reference_path.read_bytes())
    assert reference['passed'] and {'-GXLEN=64', '-GHAS_H=1', '-GHAS_MMU=1'} <= set(model['params'])
    config, linker = 'config/reference/sail-rv23.json', 'scripts/reference/upstream_htif.ld'
    inputs = source_inputs([BASE, config, linker, 'scripts/run_sail_event_comparison.py',
                            'tb/fixtures/bootrom/bootrom_host_jump64.hex'])
    inputs.update(model['inputs'])
    inputs.update(reference['inputs'])
    inputs.update({model['binary']: model['binary_sha256'], reference['binary']: reference['binary_sha256']})
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    metadata = dict(inputs=inputs, model=model, reference_report_sha256=sha(reference_path),
                    generator_sha256=sha(__file__), cases=cases)
    artifacts = dict(source=source, elf=elf, sail_trace=sail_csv, rtl_trace=rtl_csv)
    if args.check:
        report = json.loads(report_path.read_bytes())
        assert report['passed'] and all(report[key] == value for key, value in metadata.items())
        assert source.read_text(encoding='utf-8') == code
        for key, path in artifacts.items():
            assert sha(path) == report[key + '_sha256'], path
        assert trace_evidence(sail_csv, rtl_csv, cases) == (report['events'], report['traps'])
        for phase in ('compile', 'sail', 'rtl'):
            record = report[phase]
            assert record['passed'] and record['exit_code'] == 0
            assert sha(ROOT / record['log']) == record['log_sha256']
        assert 'PASS Sail HTIF' in (ROOT / report['sail']['log']).read_text(encoding='utf-8')
        assert 'PASS rv32_program_tb' in (ROOT / report['rtl']['log']).read_text(encoding='utf-8')
        print('PASS current implicit PTE-read MXR evidence', flush=True)
        return

    source.write_text(code, encoding='utf-8')
    with Simulator() as sim:
        compile_run, _ = sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64gcvh', '-mabi=lp64d',
            '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,--build-id=none',
            '-T', linker, source, '-o', elf], folder / 'compile.log', 60)
        elf_digest = sha(elf)
        original_path = sim.env['PATH']
        sim.env['PATH'] = 'C:/rv_toolchains/cygwin-rv23/bin;' + original_path
        sail, sail_log = sim.run([ROOT / reference['binary'], '--config', ROOT / config, '--commit-csv',
            sail_csv, '--inst-limit', '1000000', elf], folder / 'sail.log', 180)
        sim.env['PATH'] = original_path
        rtl, rtl_log = sim.run([ROOT / model['binary'], f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={rtl_csv.relative_to(ROOT).as_posix()}', '+quiet_commit', '+htif',
            '+timeout_cycles=300000', '+expected_exit_code=0'], folder / 'rtl.log', 120)
    assert 'PASS Sail HTIF' in sail_log and 'PASS rv32_program_tb' in rtl_log
    assert sha(elf) == elf_digest
    for name, digest in inputs.items():
        assert sha(ROOT / name) == digest, name
    events, traps = trace_evidence(sail_csv, rtl_csv, cases)
    dump(report_path, dict(passed=True, **metadata,
         **{key + '_sha256': sha(path) for key, path in artifacts.items()},
         compile=compile_run, sail=sail, rtl=rtl, events=events, traps=traps))
    print(f'PASS implicit PTE-read MXR on Sail and RTL: {len(cases)} cases, {len(traps)} traps, {events} events', flush=True)


if __name__ == '__main__':
    main()

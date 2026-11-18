"""Native scalar/vector FP shared frm/fflags and inactive element contract."""
import argparse
import copy
import json
import subprocess
from fractions import Fraction

from audit_hv_sail_fixture import check_fixture
from fp_reference import BinaryFP
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs

FOLDER = ROOT / 'out/rva23/scalar_vector_fp_state'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/fp_reference.py']
SELECTIONS = [('all', 4, 0, 15), ('masked', 4, 0, 14), ('restart', 4, 1, 15),
    ('tail', 1, 0, 15), ('zero', 0, 0, 15), ('completed', 2, 2, 15),
    ('no_mask_bits', 4, 0, 0), ('last_only', 4, 3, 15)]


def cases(width):
    fp = BinaryFP(8, 23) if width == 32 else BinaryFP(11, 52)
    one, two, three = [fp.pack(Fraction(n), 0)[0] for n in (1, 2, 3)]
    tiny = fp.pack(Fraction(1, 1 << (fp.fb + 2)), 0)[0]
    plan = []
    for op in ('add', 'div'):
        a = [fp.inf | 1, fp.inf - 1, one, one | fp.signbit] if op == 'add' else [0, one, one, 1]
        b = [one, fp.inf - 1, tiny, tiny | fp.signbit] if op == 'add' else [0, 0, three, two]
        for rm in range(5):
            for selection, vl, start, mask in SELECTIONS:
                payload, flags, active = bytearray(b'\xa5' * 32), 5, 0
                for lane in range(start, vl):
                    if mask >> lane & 1:
                        value, accrued = (fp.add if op == 'add' else fp.divide)(a[lane], b[lane], rm)
                        payload[lane * (width // 8):(lane + 1) * (width // 8)] = value.to_bytes(width // 8, 'little')
                        flags |= accrued
                        active += 1
                scalar, scalar_flags = fp.add(one, tiny, rm)
                assert scalar_flags == 1
                plan.append(dict(width=width, op=op, rm=rm, selection=selection, vl=vl, start=start,
                    mask=mask, a=a, b=b, one=one, tiny=tiny, scalar=scalar, active=active,
                    vector_flags=flags, expected_words=[int.from_bytes(payload[i:i+8], 'little') for i in range(0, 32, 8)]))
    assert len(plan) == 80
    return plan


def observations(plan):
    records = {}
    width = plan[0]['width']
    for index, case in enumerate(plan, 1):
        fcsr = lambda flags: case['rm'] << 5 | flags
        records[f'before_{index}'] = (0x003023f3, fcsr(5))
        records[f'scalar_{index}'] = ((0xe0000053 if width == 32 else 0xe2000053) | 2 << 15 | 7 << 7, case['scalar'])
        records[f'after_vector_{index}'] = (0x003023f3, fcsr(case['vector_flags']))
        records[f'start_{index}'] = (0x008023f3, 0)
        records[f'vcsr_{index}'] = (0x00f023f3, 5)
        records[f'after_scalar_{index}'] = (0x003023f3, fcsr(case['vector_flags'] | 8))
        for offset, value in zip(range(0, 32, 8), case['expected_words']):
            records[f'word_{index}_{offset}'] = (offset << 20 | 5 << 15 | 3 << 12 | 7 << 7 | 3, value)
    return records


def fixture(plan):
    width = plan[0]['width']
    suffix, move = ('s', 'w') if width == 32 else ('d', 'd')
    lines = ['.section .text.init,"ax"', '.option norvc', '.globl _start', '_start:',
        'la t0,fail', 'csrw mtvec,t0', 'li t0,0x6600', 'csrw mstatus,t0']
    data = ['initial:', '.fill 32,1,0xa5']
    records = observations(plan)
    def capture(label, instruction):
        value = records[label][1]
        lines.extend([f'{label}:{instruction}', f'li t3,{value:#x}', 'bne t2,t3,fail'])
    for index, case in enumerate(plan, 1):
        for name in ('a', 'b'):
            raw = b''.join(value.to_bytes(width // 8, 'little') for value in case[name]).ljust(32, b'\0')
            data += ['.balign 16', f'{name}_{index}:', '.byte ' + ','.join(map(str, raw))]
        data += ['.balign 16', f'mask_{index}:', f'.byte {case["mask"]}', '.fill 15,1,0']
        lines += ['csrwi vstart,0', f'vsetivli zero,4,e{width},m2,tu,mu',
            f'la t0,a_{index}', 'vl2re8.v v16,(t0)', f'la t0,b_{index}', 'vl2re8.v v24,(t0)',
            'la t0,initial', 'vl2re8.v v8,(t0)', f'la t0,mask_{index}', 'vl1re8.v v0,(t0)',
            f'vsetivli zero,{case["vl"]},e{width},m2,tu,mu', 'csrwi vcsr,5',
            f'csrwi frm,{case["rm"]}', 'csrwi fflags,4', f'li t0,{case["one"]:#x}',
            f'fmv.{move}.x ft0,t0', f'li t0,{case["tiny"]:#x}', f'fmv.{move}.x ft1,t0',
            f'fadd.{suffix} ft2,ft0,ft1,dyn']
        capture(f'before_{index}', 'csrr t2,fcsr')
        capture(f'scalar_{index}', f'fmv.x.{move} t2,ft2')
        lines += [f'csrwi vstart,{case["start"]}', f'probe_{index}:vf{case["op"]}.vv v8,v16,v24,v0.t']
        capture(f'after_vector_{index}', 'csrr t2,fcsr')
        capture(f'start_{index}', 'csrr t2,vstart')
        capture(f'vcsr_{index}', 'csrr t2,vcsr')
        lines += [f'fmv.{move}.x ft3,zero', f'fdiv.{suffix} ft4,ft0,ft3,rne']
        capture(f'after_scalar_{index}', 'csrr t2,fcsr')
        lines += ['la t0,observed', 'vs2r.v v8,(t0)']
        for offset in range(0, 32, 8):
            capture(f'word_{index}_{offset}', f'ld t2,{offset}(t0)')
    lines += ['li t1,1', 'j finish', 'fail:li t1,3', 'finish:', 'la t0,tohost', 'sd t1,0(t0)',
        'halt:j halt', '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0', '.section .bss,"aw",@nobits', '.balign 32',
        'observed:.space 32', '.section .rodata,"a"', '.balign 16', *data]
    return '\n'.join(lines) + '\n'


def inspect(rows, plan, symbols):
    targets = {symbols[name]: value for name, value in observations(plan).items()}
    probes = {symbols[f'probe_{index}']: case for index, case in enumerate(plan, 1)}
    seen, executed = set(), set()
    for index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        assert pc < 0x80000000 or row['trap'] == '0', row
        if pc in targets:
            instruction, value = targets[pc]
            assert pc not in seen and word == instruction, row
            assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '7'
            assert int(row['wdata'], 16) == value, row
            seen.add(pc)
        if pc in probes:
            case = probes[pc]
            expected = (0 if case['op'] == 'add' else 0x20) << 26 | 16 << 20 | 24 << 15 | 1 << 12 | 8 << 7 | 0x57
            assert pc not in executed and word == expected
            assert int(rows[index + 1]['pc'], 16) == pc + 4
            executed.add(pc)
    assert seen == set(targets) and executed == set(probes)
    return dict(probes=len(plan), observations=len(seen), destination_words=4 * len(plan),
        active_elements=sum(case['active'] for case in plan), selection_modes=sorted({case['selection'] for case in plan}))


def verifier(plan, folder):
    def verify(sail_trace, rtl_trace):
        rows = read_csv(rtl_trace)
        events, mismatch = compare(read_csv(sail_trace), rows)
        assert mismatch is None, mismatch
        nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(folder / 'test.elf')], text=True)
        symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
        result, controls = inspect(rows, plan, symbols), []
        for name in ('before_1', 'scalar_1', 'after_vector_1', 'start_1', 'vcsr_1', 'after_scalar_1', 'word_1_0'):
            broken = copy.deepcopy(rows)
            row = next(row for row in broken if int(row['pc'], 16) == symbols[name])
            row['wdata'] = f"{int(row['wdata'], 16) ^ 1:016x}"
            try:
                inspect(broken, plan, symbols)
            except AssertionError:
                controls.append(name)
            else:
                raise AssertionError(f'Incorrect shared FP state accepted: {name}')
        return dict(**result, matched_events=events, rejected_mutations=controls)
    return verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    top = dict(passed=False, complete_profile_validation=False, generator_sha256=sha(__file__),
        inputs=source_inputs(DEPENDENCIES), cases=[], scope='Finite M-mode scalar/vector FP shared frm/fflags, masked/prestart/tail and zero/completed vl under tu/mu; S/D m2, vfadd/vfdiv. Not all vector operations, LMUL, guest permissions, faults, timing or interrupt schedules')
    if args.check:
        saved = json.loads((FOLDER / 'report.json').read_bytes())
        assert saved['passed'] and saved['generator_sha256'] == top['generator_sha256'] and saved['inputs'] == top['inputs']
        assert len(saved['cases']) == 2
    for index, width in enumerate((32, 64)):
        plan = cases(width)
        folder = FOLDER / str(width)
        folder.mkdir(exist_ok=True)
        source, verify = folder / 'test.S', verifier(plan, folder)
        if args.check:
            outcome = check_fixture(folder, __file__, fixture(plan), verify)
            old = saved['cases'][index]
            assert old['width'] == width and old['report_sha256'] == sha(folder / 'report.json') and old['outcomes'] == outcome
        else:
            source.write_text(fixture(plan), encoding='utf-8')
            outcome = run_fixture(source, folder, __file__, verify, source_dependencies=DEPENDENCIES, timeout_cycles=3000000)
        top['cases'].append(dict(width=width, report_sha256=sha(folder / 'report.json'), outcomes=outcome))
        if not args.check:
            dump(FOLDER / 'report.json', top)
        print('PASS scalar/vector shared FP', width, outcome['probes'], 'probes;', outcome['matched_events'], 'events', flush=True)
    top['passed'] = True
    if not args.check:
        dump(FOLDER / 'report.json', top)


if __name__ == '__main__':
    main()

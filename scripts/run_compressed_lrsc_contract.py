"""Finite constrained LR/SC progress with actual compressed I/retry instructions."""
import argparse
import copy
import json
import subprocess

from audit_hv_sail_fixture import check_fixture
from audit_rv64c_contract import decode as decode_c
from audit_rv64i_compute_control import sx
from audit_rv64i_memory_values import LOADS, STORES, initial_memory
from audit_rv64m_contract import MASK
from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, dump, sha, source_inputs


FOLDER = ROOT / 'out/rva23/compressed_lrsc_contract'
DEPENDENCIES = ['scripts/audit_hv_sail_fixture.py', 'scripts/audit_rv64c_contract.py',
    'scripts/audit_rv64i_compute_control.py', 'scripts/audit_rv64i_memory_values.py',
    'scripts/audit_rv64m_contract.py']
BODIES = {
    'minimal': ['c.addi a0,1'],
    'dense': ['c.mv a2,a0', 'c.addi a2,1', 'c.mv a0,a2', 'c.xor a0,a3',
        'c.or a0,a3', 'c.and a0,a4', 'c.sub a0,a3', 'c.add a0,a3',
        'c.andi a0,-1', 'c.mv a2,a0', 'c.mv a0,a2', 'c.xor a0,a3', 'c.or a0,a3']}


def cases():
    return [dict(shape=shape, size=size, offset=offset, position=position)
        for shape in BODIES for size in (4, 8)
        for offset in range(0, 64, size) for position in (0, 32, 62)]


def fixture():
    lines = ['.section .text.init,"ax"', '.option norvc', '.option norelax',
        '.globl _start', '_start:', 'la t0,fail', 'csrw mtvec,t0']
    for index, case in enumerate(cases()):
        suffix = 'w' if case['size'] == 4 else 'd'
        lines += [f'li s0,{0x80070000 + case["offset"]:#x}', f's{suffix} zero,0(s0)',
            'li s1,16', 'li a0,1', 'li a3,0', 'li a4,-1',
            f'j sc_{index}', '.balign 64,0',
            f'.space {case["position"]}', f'loop_{index}: lr.{suffix}.aq a0,(s0)',
            '.option rvc', *BODIES[case['shape']], '.option norvc',
            f'sc_{index}: sc.{suffix}.rl a1,a0,(s0)', '.option rvc',
            f'retry_{index}: c.bnez a1,loop_{index}', '.option norvc',
            f'exit_{index}: addi s1,s1,-1', f'bnez s1,loop_{index}',
            f'check_{index}: l{suffix} t1,0(s0)', 'li t2,16', 'bne t1,t2,fail']
    lines += ['li t1,1', 'j finish', '.balign 4', 'fail:li t1,3', 'finish:',
        'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt', '.section .tohost,"aw"',
        '.balign 8', '.globl tohost,fromhost', 'tohost:.dword 0', 'fromhost:.dword 0']
    return '\n'.join(lines) + '\n'


def layout(symbols, memory):
    outcomes = []
    for index, case in enumerate(cases()):
        pc, start, stop = symbols[f'loop_{index}'], symbols[f'loop_{index}'], symbols[f'exit_{index}']
        assert start % 64 == case['position']
        names = []
        while pc < stop:
            word = memory[pc] | memory[pc + 1] << 8
            if word & 3 == 3:
                word |= memory[pc + 2] << 16 | memory[pc + 3] << 24
                assert word & 127 == 0x2f
                name = {2: 'lr', 3: 'sc'}[word >> 27]
                assert pc == symbols[f'{"loop" if name == "lr" else "sc"}_{index}']
                names.append(name)
                pc += 4
            else:
                sample = [0] * 32
                sample[11] = 1  # Statically verify the failure path even when no SC fails.
                item = decode_c(word, pc, sample)
                assert item is not None
                names.append(item[0])
                if pc == symbols[f'retry_{index}']:
                    assert item[0] == 'bnez' and ((word >> 7) & 7) + 8 == 11
                    assert item[3] == start
                pc += 2
        expected = ['lr', *[line.split()[0][2:] for line in BODIES[case['shape']]], 'sc', 'bnez']
        assert names == expected and pc == stop
        assert len(names) == (4 if case['shape'] == 'minimal' else 16)
        assert stop - start == (12 if case['shape'] == 'minimal' else 36)
        outcomes.append(dict(**case, instructions=len(names), bytes=stop - start))
    return outcomes


def inspect(rows, symbols, initial):
    plan = cases()
    starts = {symbols[f'loop_{i}']: i for i in range(len(plan))}
    scs = {symbols[f'sc_{i}']: i for i in range(len(plan))}
    checks = {symbols[f'check_{i}']: i for i in range(len(plan))}
    memory, registers = initial.copy(), [None] * 32
    registers[0] = 0
    outcomes = [dict(successes=0, attempts=0, lr=0, forced_no_lr=0, final_loads=0) for _ in plan]
    pending, compressed, atomic_indices = None, {}, {'lr': [], 'sc': [], 'check': [], 'compressed': []}
    def read(address, size):
        assert all(address + i in memory for i in range(size)), (hex(address), size)
        return sum(memory[address + i] << (8 * i) for i in range(size))
    def write(address, size, value):
        for i in range(size):
            memory[address + i] = (value >> (8 * i)) & 255
    for index, row in enumerate(rows):
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if pc >= 0x80000000:
            assert row['trap'] == '0', row
            if pc in starts or pc in scs:
                case_index = starts[pc] if pc in starts else scs[pc]
                case, stats = plan[case_index], outcomes[case_index]
                size = case['size']
                address = registers[8]
                assert address == 0x80070000 + case['offset'] and address % size == 0
                assert word & 127 == 0x2f and (word >> 15) & 31 == 8
                assert (word >> 12) & 7 == (2 if size == 4 else 3)
                if pc in starts:
                    assert word >> 27 == 2 and (word >> 25) & 3 == 2 and (word >> 20) & 31 == 0
                    value = read(address, size)
                    value = (sx(value, 32) if size == 4 else value) & MASK
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '10'
                    assert int(row['wdata'], 16) == value, row
                    pending = (case_index, address, size)
                    stats['lr'] += 1
                    atomic_indices['lr'].append(index)
                else:
                    assert word >> 27 == 3 and (word >> 25) & 3 == 1 and (word >> 20) & 31 == 10
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and row['rd'] == '11'
                    value = int(row['wdata'], 16)
                    if pending is None:
                        # One deliberate SC without LR enters the failure/retry
                        # edge before the 16 successful constrained invocations.
                        assert stats['attempts'] == stats['lr'] == stats['forced_no_lr'] == 0
                        assert value != 0
                        stats['forced_no_lr'] += 1
                    else:
                        assert pending == (case_index, address, size)
                    if size == 4:
                        assert value == sx(value, 32) & MASK
                    assert registers[10] == (read(address, size) + 1) & MASK
                    stats['attempts'] += 1
                    if value == 0:
                        write(address, size, registers[10])
                        stats['successes'] += 1
                    pending = None
                    atomic_indices['sc'].append(index)
            elif word & 3 != 3:
                item = decode_c(word, pc, registers)
                assert item is not None
                name, rd, value, target, taken = item
                if value is not None and rd:
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                    assert int(row['wdata'], 16) == value, row
                else:
                    assert row['rd_write'] == '0' or (row['rd_fp'] == '0' and row['rd'] == '0')
                assert int(rows[index + 1]['pc'], 16) == target, row
                compressed[name] = compressed.get(name, 0) + 1
                atomic_indices['compressed'].append(index)
            elif word & 127 in (3, 0x23):
                load, f3 = word & 127 == 3, (word >> 12) & 7
                base = registers[(word >> 15) & 31]
                assert base is not None
                imm = word >> 20 if load else (word >> 25) << 5 | (word >> 7) & 31
                address = (base + sx(imm, 12)) & MASK
                if load:
                    _, size, sign = LOADS[f3]
                    value = read(address, size)
                    value = (sx(value, size * 8) if sign else value) & MASK
                    rd = (word >> 7) & 31
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                    assert int(row['wdata'], 16) == value
                    if pc in checks:
                        stats = outcomes[checks[pc]]
                        assert stats['successes'] == 16 and value == 16
                        stats['final_loads'] += 1
                        atomic_indices['check'].append(index)
                else:
                    _, size = STORES[f3]
                    value = registers[(word >> 20) & 31]
                    assert value is not None
                    write(address, size, value)
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    assert pending is None
    assert all(item['successes'] == 16 and item['final_loads'] == 1 and item['forced_no_lr'] == 1
               and item['lr'] + 1 == item['attempts'] >= 17 for item in outcomes)
    return dict(placements=len(plan), successful_updates=sum(item['successes'] for item in outcomes),
        sc_attempts=sum(item['attempts'] for item in outcomes),
        failed_sc=sum(item['attempts'] - item['successes'] for item in outcomes),
        forced_no_lr_attempts=sum(item['forced_no_lr'] for item in outcomes),
        compressed_retirements=compressed, cases=outcomes), atomic_indices


def verifier(sail_trace, rtl_trace):
    rows = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), rows)
    # This exact trace gate describes this implementation/run. The ISA also
    # permits spurious SC failure; the independent byte oracle consumes status.
    assert mismatch is None, mismatch
    nm = subprocess.check_output([str(GCC / 'riscv-none-elf-nm.exe'), '-n', str(FOLDER / 'test.elf')], text=True)
    symbols = {parts[2]: int(parts[0], 16) for line in nm.splitlines() if len(parts := line.split()) == 3}
    memory = initial_memory(FOLDER / 'test.elf')
    footprints = layout(symbols, memory)
    result, indices = inspect(rows, symbols, memory)
    controls = []
    for kind in ('lr', 'sc', 'check', 'compressed'):
        broken = copy.deepcopy(rows)
        index = (next(i for i in indices[kind] if rows[i]['rd_write'] == '1' and rows[i]['rd'] != '0')
                 if kind == 'compressed' else indices[kind][0])
        broken[index]['wdata'] = f"{int(broken[index]['wdata'], 16) ^ 1:016x}"
        try:
            inspect(broken, symbols, memory)
        except AssertionError:
            controls.append(kind + '_value')
        else:
            raise AssertionError(f'Incorrect {kind} value accepted')
    broken = copy.deepcopy(rows)
    index = next(i for i in indices['compressed'] if int(rows[i]['pc'], 16) == symbols['retry_0'])
    broken[index + 1]['pc'] = f"{int(broken[index + 1]['pc'], 16) ^ 2:016x}"
    try:
        inspect(broken, symbols, memory)
    except AssertionError:
        controls.append('retry_next_pc')
    else:
        raise AssertionError('Incorrect compressed retry target accepted')
    broken_memory = memory.copy()
    pc = symbols['retry_0']
    broken_memory[pc], broken_memory[pc + 1] = 1, 0
    try:
        layout(symbols, broken_memory)
    except AssertionError:
        controls.append('retry_layout')
    else:
        raise AssertionError('Wrong retry layout accepted')
    return dict(**result, matched_events=events, footprints=footprints, rejected_mutations=controls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    if args.check:
        result = check_fixture(FOLDER, __file__, fixture(), verifier)
    else:
        source = FOLDER / 'test.S'
        source.write_text(fixture(), encoding='utf-8')
        result = run_fixture(source, FOLDER, __file__, verifier,
            source_dependencies=DEPENDENCIES, timeout_cycles=3000000)
    print('PASS compressed constrained LR/SC:', result['placements'], 'placements;',
        result['successful_updates'], 'updates;', result['matched_events'], 'Sail/RTL events;',
        result['failed_sc'], 'failed SC;', len(result['rejected_mutations']), 'rejected mutations', flush=True)


if __name__ == '__main__':
    main()

"""Check finite bare-mode RV64I memory traces against ELF-backed byte memory."""
import copy
import json
import struct

from audit_rv64i_compute_control import sx
from audit_rv64m_contract import MASK
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT, dump, sha, source_inputs


LOADS = {0: ('lb', 1, True), 1: ('lh', 2, True), 2: ('lw', 4, True),
         3: ('ld', 8, False), 4: ('lbu', 1, False), 5: ('lhu', 2, False), 6: ('lwu', 4, False)}
STORES = {0: ('sb', 1), 1: ('sh', 2), 2: ('sw', 4), 3: ('sd', 8)}
NAMES = {item[0] for item in LOADS.values()} | {item[0] for item in STORES.values()}
CASES = NAMES | {'ld_st', 'st_ld', 'ma_data'}


def expand_memory(word):
    """Decode integer C memory formats so intervening C stores are not lost."""
    if word & 3 == 3:
        return word, ''
    quadrant, funct3 = word & 3, (word >> 13) & 7
    if quadrant not in (0, 2) or funct3 not in (1, 2, 3, 5, 6, 7):
        return word, ''
    assert funct3 in (2, 3, 6, 7), 'FP compressed memory is outside this integer oracle'
    load, double = funct3 in (2, 3), funct3 in (3, 7)
    if quadrant == 0:
        rs1, other = 8 + ((word >> 7) & 7), 8 + ((word >> 2) & 7)
        offset = (((word >> 10) & 7) << 3)
        offset |= (((word >> 5) & 3) << 6) if double else (((word >> 5) & 1) << 6 | ((word >> 6) & 1) << 2)
    else:
        rs1 = 2
        other = ((word >> 7) & 31) if load else ((word >> 2) & 31)
        if load:
            assert other != 0
            offset = ((word >> 12) & 1) << 5
            offset |= ((((word >> 2) & 7) << 6) | (((word >> 5) & 3) << 3)) if double else (
                (((word >> 2) & 3) << 6) | (((word >> 4) & 7) << 2))
        else:
            offset = ((((word >> 7) & 7) << 6) | (((word >> 10) & 7) << 3)) if double else (
                (((word >> 7) & 3) << 6) | (((word >> 9) & 15) << 2))
    size_code = 3 if double else 2
    if load:
        expanded = offset << 20 | rs1 << 15 | size_code << 12 | other << 7 | 3
    else:
        expanded = (offset >> 5) << 25 | other << 20 | rs1 << 15 | size_code << 12 | (offset & 31) << 7 | 0x23
    return expanded, 'c.sp.' if quadrant == 2 else 'c.'


def initial_memory(elf):
    data = elf.read_bytes()
    assert data[:7] == b'\x7fELF\x02\x01\x01'
    header = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)
    assert header[1] == 243 and header[8] == 56
    memory = {}
    for index in range(header[9]):
        kind, _, offset, va, pa, size, mem_size, _ = struct.unpack_from(
            '<IIQQQQQQ', data, header[4] + index * header[8])
        if kind != 1:
            continue
        assert va == pa and size <= mem_size and offset + size <= len(data)
        # Only file-backed bytes are initially known. Unwritten NOBITS bytes
        # are not silently assumed reset-cleared by this hardware oracle.
        memory.update({pa + i: value for i, value in enumerate(data[offset:offset + size])})
    assert memory
    return memory


def inspect(rows, initial):
    memory, writers, stores = initial.copy(), {}, {}
    registers = [None] * 32
    registers[0] = 0
    coverage = {}
    for index, row in enumerate(rows):
        word, prefix = expand_memory(int(row['instruction'], 16))
        pc = int(row['pc'], 16)
        opcode, funct3 = word & 0x7f, (word >> 12) & 7
        load = opcode == 3 and funct3 in LOADS
        store = opcode == 0x23 and funct3 in STORES
        if pc >= 0x80000000 and (load or store):
            assert row['trap'] == '0', row
            rs1, rs2, rd = (word >> 15) & 31, (word >> 20) & 31, (word >> 7) & 31
            base = registers[rs1]
            assert base is not None, row
            immediate = word >> 20 if load else ((word >> 25) << 5 | (word >> 7) & 31)
            address = (base + sx(immediate, 12)) & MASK
            if load:
                name, size, sign_extend = LOADS[funct3]
            else:
                name, size = STORES[funct3]
            name = 'c.' + name + 'sp' if prefix == 'c.sp.' else prefix + name
            stats = coverage.setdefault(name, dict(operations=0, misaligned=0, negative_offset=0,
                zero_destination=0, prior_store_bytes_read=0, observed_stores=0))
            stats['operations'] += 1
            stats['misaligned'] += address % size != 0
            stats['negative_offset'] += sx(immediate, 12) < 0
            addresses = [(address + offset) & MASK for offset in range(size)]
            if load:
                assert all(byte in memory for byte in addresses), (name, hex(address), row)
                raw = sum(memory[byte] << (8 * offset) for offset, byte in enumerate(addresses))
                value = (sx(raw, size * 8) if sign_extend else raw) & MASK
                if rd:
                    assert row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']) == rd
                    assert int(row['wdata'], 16) == value, (name, hex(address), hex(value), row)
                else:
                    stats['zero_destination'] += 1
                for byte in addresses:
                    if byte in writers:
                        stores[writers[byte]]['observed'].add(byte)
                        stats['prior_store_bytes_read'] += 1
            else:
                value = registers[rs2]
                assert value is not None, row
                stores[index] = dict(name=name, observed=set())
                for offset, byte in enumerate(addresses):
                    memory[byte] = (value >> (8 * offset)) & 255
                    writers[byte] = index
        if row['trap'] == '0' and row['rd_write'] == '1' and row['rd_fp'] == '0' and int(row['rd']):
            registers[int(row['rd'])] = int(row['wdata'], 16)
    for store in stores.values():
        coverage[store['name']]['observed_stores'] += bool(store['observed'])
    return coverage


def main():
    report = ROOT / 'out/rva23/sail_upstream_comparison/report.json'
    base = json.loads(report.read_bytes())
    assert base['passed'] and source_inputs(base['inputs']) == base['inputs']
    model, reference = base['model'], base['reference']
    assert source_inputs(model['inputs']) == model['inputs']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    assert sha(ROOT / reference['binary']) == reference['binary_sha256']
    assert {'-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'} <= set(model['params'])
    cases = [case for case in base['cases'] if case['name'] in {'rv64ui/' + name for name in CASES}]
    assert len(cases) == len(CASES) == 14
    artifacts, outcomes, controls, store_controls = {}, {}, [], []
    for case in cases:
        assert case['reference_passed'] and case['rtl_passed']
        assert case['rtl_model_sha256'] == model['binary_sha256']
        assert case['reference_binary_sha256'] == reference['binary_sha256']
        for key in ('elf', 'rtl_trace', 'sail_trace', 'sail_log'):
            assert sha(ROOT / case[key]) == case[key + '_sha256']
            artifacts[case[key]] = case[key + '_sha256']
        run = case['rtl']
        assert run['passed'] and run['exit_code'] == 0 and sha(ROOT / run['log']) == run['log_sha256']
        artifacts[run['log']] = run['log_sha256']
        actual, sail = read_csv(ROOT / case['rtl_trace']), read_csv(ROOT / case['sail_trace'])
        events, mismatch = compare(sail, actual)
        assert mismatch is None, mismatch
        memory = initial_memory(ROOT / case['elf'])
        coverage = inspect(actual, memory)
        name = case['name'].split('/')[1]
        if name in NAMES:
            assert coverage[name]['operations'] > 0
        if name in {item[0] for item in STORES.values()}:
            assert coverage[name]['observed_stores'] > 0
        outcomes[name] = dict(matched_events=events, coverage=coverage)
        broken = copy.deepcopy(actual)
        row = next(row for row in broken if int(row['pc'], 16) >= 0x80000000
                   and int(row['instruction'], 16) & 0x7f == 3 and row['rd_write'] == '1'
                   and int(row['rd']) != 0)
        row['wdata'] = f"{int(row['wdata'], 16) ^ 1:016x}"
        try:
            inspect(broken, memory)
        except AssertionError:
            controls.append(name)
        else:
            raise AssertionError(f'Incorrect load accepted: {name}')
        if name in {item[0] for item in STORES.values()}:
            broken = copy.deepcopy(actual)
            size_code = next(code for code, item in STORES.items() if item[0] == name)
            row = next(row for row in broken if int(row['pc'], 16) >= 0x80000000
                       and int(row['instruction'], 16) & 0x7f == 0x23
                       and (int(row['instruction'], 16) >> 12) & 7 == size_code)
            # Change S-immediate bit 0, then let later loads expose the wrong byte map.
            row['instruction'] = f"{int(row['instruction'], 16) ^ 0x80:08x}"
            try:
                inspect(broken, memory)
            except AssertionError:
                store_controls.append(name)
            else:
                raise AssertionError(f'Incorrect store address accepted: {name}')
    dump(ROOT / 'out/rva23/rv64i_memory_value_audit.json', dict(
        passed=True, complete_profile_validation=False,
        scope='Finite bare-mode byte values from ELF and committed scalar stores; bus request order, unread store bytes, traps and concurrency are separate',
        base_report_sha256=sha(report), audit_sha256=sha(__file__),
        helper_inputs=source_inputs(['scripts/audit_rv64m_contract.py', 'scripts/audit_rv64i_compute_control.py']),
        artifacts=artifacts, outcomes=outcomes, rejected_load_mutations=controls,
        rejected_store_address_mutations=store_controls))
    print('PASS RV64I byte-memory oracle: 14 ELFs, 11 load/store forms, 14 rejected load and 4 store-address mutations')


if __name__ == '__main__':
    main()

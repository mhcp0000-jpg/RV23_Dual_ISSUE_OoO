"""Compare same-PC scalar and indexed vector page-fault retries."""

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT


FOLDER = 'out/rva23/indexed_memory_restart'
BASE = 'sw/tests/rv64_atomic_sv39.S'
BODY = 'sw/tests/rv64_indexed_restart_body.S'
PROBES = {
    0x0007b283: (13, 0x40004000),  # ld t0,0(a5)
    0x06c47407: (13, 0x40004008),  # vluxei64.v v8,(s0),v12
    0x06c47427: (15, 0x40004008),  # vsuxei64.v v8,(s0),v12
    0x0ec47427: (15, 0x40004008),  # vsoxei64.v v8,(s0),v12
}
MASKED = (0x04c47407, 0x04c47427)
ORDERED_READ = 0x0ec47407  # vloxei64.v v8,(s0),v12


def fixture():
    header = (ROOT / BASE).read_text(encoding='utf-8').split('s_entry:\n', 1)[0]
    assert header.count('  li t0,0x800\n') == 1
    return header.replace('  li t0,0x800\n', '  li t0,0xe00\n') + (ROOT / BODY).read_text(encoding='utf-8')


def verify_traces(sail_trace, rtl_trace):
    actual = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), actual)
    assert mismatch is None, mismatch
    faults, retries, indices, masked = [], [], [], []
    ordered_reads = 0
    for row in actual:
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if pc < 0x80000000:
            continue
        if row['trap'] == '1':
            assert PROBES[word] == (int(row['cause']), int(row['tval'], 16))
            faults.append((pc, word))
        elif word in PROBES:
            retries.append((pc, word))
        elif word in MASKED:
            masked.append(word)
        elif word == ORDERED_READ:
            ordered_reads += 1
        elif word == 0x00802ef3:  # csrr t4,vstart in the trap handler
            indices.append(int(row['wdata'], 16))
    assert [word for _, word in faults] == list(PROBES)
    assert retries == faults and indices == [0, 2, 2, 2] and tuple(masked) == MASKED
    assert ordered_reads == 1
    return dict(same_pc_retries=len(retries), fault_indices=indices,
                masked_accesses=len(masked), ordered_reads=ordered_reads, matched_events=events)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'test.S'
    source.write_text(fixture(), encoding='utf-8')
    outcomes = run_fixture(source, folder, __file__, verify_traces, source_dependencies=(BASE, BODY))
    print('PASS scalar and indexed vector memory restart', outcomes, flush=True)


if __name__ == '__main__':
    main()

"""Check all whole-register move widths and restart boundaries at VL=0."""

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT


FOLDER = 'out/rva23/vector_whole_moves'
SOURCE = 'sw/tests/rv64_vector_whole_moves.S'
MOVES = {0x9e803857 | ((count - 1) << 15): count for count in (1, 2, 4, 8)}
BOUNDARY_MARKER = 0x07b00013  # addi zero,zero,123
SHARED_MOVES = [count for count in MOVES.values() for _ in range(12)]
EXTENDED_MOVES = [count for count in MOVES.values() for _ in range(5 if count < 8 else 4)]


def probe_cases(rows, *, trap):
    moves = []
    for row in rows:
        if int(row['pc'], 16) < 0x80000000:
            continue
        word = int(row['instruction'], 16)
        is_trap = row['trap'] == '1'
        if is_trap:
            assert word in MOVES and int(row['cause']) == 2, row
        if word in MOVES:
            assert is_trap == trap, row
            moves.append(MOVES[word])
    return moves


def split_trace(trace):
    rows = read_csv(trace)
    markers = [index for index, row in enumerate(rows)
               if int(row['instruction'], 16) == BOUNDARY_MARKER]
    assert len(markers) == 1, markers
    end = markers[0] + 1
    return rows[:end], rows[end:]


def verify_traces(sail_trace, rtl_trace):
    sail_shared, sail_extended = split_trace(sail_trace)
    rtl_shared, rtl_extended = split_trace(rtl_trace)
    events, mismatch = compare(sail_shared, rtl_shared)
    assert mismatch is None, mismatch
    assert probe_cases(rtl_shared, trap=False) == SHARED_MOVES
    assert probe_cases(rtl_extended, trap=False) == EXTENDED_MOVES
    assert probe_cases(sail_extended, trap=True) == EXTENDED_MOVES
    return dict(shared_moves=len(SHARED_MOVES), extended_moves=len(EXTENDED_MOVES),
                checked_rtl_bytes=(len(SHARED_MOVES) + len(EXTENDED_MOVES)) * 128,
                matched_events=events, reference_boundary_traps=len(EXTENDED_MOVES))


def main():
    outcomes = run_fixture(ROOT / SOURCE, ROOT / FOLDER, __file__, verify_traces,
                           timeout_cycles=1500000)
    print('PASS vector whole-register moves at VL=0', outcomes, flush=True)


if __name__ == '__main__':
    main()

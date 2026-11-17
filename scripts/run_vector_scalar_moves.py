"""Replay scalar-move boundaries on the native H/V SoC and pinned Sail."""

from run_sail_event_comparison import compare, read_csv
from run_hv_sail_fixture import run_fixture
from sim_runner import ROOT


FOLDER = 'out/rva23/vector_scalar_moves'
SOURCE = 'sw/tests/rv64_vector_scalar_moves.S'
MOVES = {
    0x42302557: ('integer', True, False),   # vmv.x.s a0,v3
    0x4206e1d7: ('integer', False, False),  # vmv.s.x v3,a3
    0x42301557: ('float', True, True),      # vfmv.f.s fa0,v3
    0x4205d1d7: ('float', False, False),   # vfmv.s.f v3,fa1
}
ILLEGAL_MOVES = [0x40302557, 0x4006e1d7, 0x40301557, 0x4005d1d7, 0x42301557, 0x4205d1d7]


def verify_traces(sail_trace, rtl_trace):
    reference, actual = read_csv(sail_trace), read_csv(rtl_trace)
    events, mismatch = compare(reference, actual)
    assert mismatch is None, mismatch
    moves = []
    traps = []
    for row in actual:
        word = int(row['instruction'], 16)
        if int(row['pc'], 16) < 0x80000000:
            continue
        if row['trap'] == '1':
            assert int(row['cause']) == 2 and int(row['tval'], 16) == word
            traps.append(word)
            continue
        if word not in MOVES:
            continue
        kind, scalar_result, fp_result = MOVES[word]
        assert int(row['rd_write']) == scalar_result
        if scalar_result:
            assert int(row['rd']) == 10 and int(row['rd_fp']) == fp_result
        moves.append((kind, scalar_result))
    assert moves == ([('integer', True), ('integer', False)] * 20
                     + [('float', True), ('float', False)] * 10) * 2, moves
    assert traps == ILLEGAL_MOVES, traps
    return dict(matched_events=events, integer_moves=80, floating_moves=40, illegal_moves=len(traps))


def main():
    outcomes = run_fixture(ROOT / SOURCE, ROOT / FOLDER, __file__, verify_traces)
    print('PASS RVV scalar-move boundaries', outcomes, flush=True)


if __name__ == '__main__':
    main()

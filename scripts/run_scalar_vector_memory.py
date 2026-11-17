"""Compare scalar and vector ordering through shared physical SRAM and VA aliases."""

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT


FOLDER = 'out/rva23/scalar_vector_memory'
SOURCE = 'sw/tests/rv64_scalar_vector_memory.S'
VLE64 = 0x0209f407  # vle64.v v8,(s3)
VSE64 = 0x0209f5a7  # vse64.v v11,(s3)
AMOADD = 0x0079352f  # amoadd.d a0,t2,(s2)


def verify_traces(sail_trace, rtl_trace):
    rtl = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), rtl)
    assert mismatch is None, mismatch
    memory = []
    for row in rtl:
        if int(row['pc'], 16) < 0x80000000:
            continue
        assert row['trap'] == '0', row
        word = int(row['instruction'], 16)
        if word in (VLE64, VSE64, AMOADD):
            memory.append(word)
    scenario = [VLE64, VSE64, VLE64, AMOADD, VLE64]
    assert memory == scenario * 8, memory
    return dict(cases=8, vector_loads=memory.count(VLE64), vector_stores=memory.count(VSE64),
                amos=memory.count(AMOADD), matched_events=events)


def main():
    outcomes = run_fixture(ROOT / SOURCE, ROOT / FOLDER, __file__, verify_traces)
    print('PASS scalar/vector shared SRAM and Sv39 aliases', outcomes, flush=True)


if __name__ == '__main__':
    main()

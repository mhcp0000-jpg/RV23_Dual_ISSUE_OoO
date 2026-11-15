"""Check legal register placement and mixed-EEW aliases in the RVV owner.

Run after run_vector_integer_engine_checks.py has built the current model.
Use vl=0 to test operand legality without data, memory traffic or timing.
"""
import json
import sys
from sim_runner import ROOT, Simulator, dump, sha

folder = ROOT / 'out/rva23/vector_source_groups'
folder.mkdir(parents=True, exist_ok=True)
origin = ROOT / 'out/rva23/vector_integer_engine/report.json'
model = json.loads(origin.read_bytes())['model']
assert sha(ROOT / model['binary']) == model['binary_sha256']
assert all(sha(ROOT / name) == value for name, value in model['inputs'].items())
packets = []
by_family = {}
fields = (31 << 7) | (31 << 15) | (31 << 20)
sew_values = (8, 16, 32, 64)
memory_width_encoding = (0, 5, 6, 7)

def packet(instruction, illegal=False):
    packets.append(f'0 {instruction:08x} 0 0 0 {int(illegal)} 2 00 0 1')

def registers(exponent):
    return 2 ** max(0, exponent)

def encoded(base, dest, src1, src2):
    return (base & ~fields) | (dest << 7) | (src1 << 15) | (src2 << 20)

def check(family, instruction, illegal):
    packet(instruction, illegal)
    counts = by_family.setdefault(family, dict(legal=0, illegal=0))
    counts['illegal' if illegal else 'legal'] += 1

def vv(family, opcode, exponents, widths):
    dest_count, a_count, b_count = map(registers, exponents)
    for a in range(0, 32, a_count):
        for b in range(0, 32, b_count):
            used_a = set(range(a, a + a_count))
            used_b = set(range(b, b + b_count))
            used = used_a | used_b
            # Keep destination overlap out of the source legality check.
            dest = next((r for r in range(0, 32, dest_count)
                         if used.isdisjoint(range(r, r + dest_count))), None)
            if dest is not None:
                check(family, encoded(opcode, dest, b, a), widths[0] != widths[1] and bool(used_a & used_b))

def store(opcode, exponent, sew, index_width, ei):
    data_count = registers(exponent) * 2
    index_count = registers(exponent + ei - sew)
    for data in range(0, 32 - data_count + 1, registers(exponent)):
        used_data = set(range(data, data + data_count))
        for index in range(0, 32, index_count):
            hit = not used_data.isdisjoint(range(index, index + index_count))
            check(f'vsuxseg2ei{index_width}', encoded(opcode, data, 11, index), sew != ei and hit)

for sew, width in enumerate(sew_values):
    for lmul in range(-3, 4):
        if lmul < 0 and width > 64 // 2**(-lmul):
            continue
        # vsetivli a2,0 with the current SEW and LMUL.
        packet(0xc0007657 | (sew << 23) | ((lmul & 7) << 20))
        if sew < 3 and lmul < 3:
            vv('vwaddu.wv', 0xd284a857, (lmul + 1, lmul + 1, lmul), (2 * width, width))
            vv('vnsrl.wv', 0xb2848a57, (lmul, lmul + 1, lmul), (2 * width, width))
            if sew == 2:
                vv('vfwadd.wv', 0xd2849857, (lmul + 1, lmul + 1, lmul), (2 * width, width))
        if sew < 3:
            vv('vwredsumu.vs', 0xc2848a57, (0, lmul, 0), (width, 2 * width))
        if -3 <= lmul + 1 - sew <= 3:
            vv('vrgatherei16.vv', 0x3a940a57, (lmul, lmul, lmul + 1 - sew), (width, 16))
        vv('vcompress.vm', 0x5e842a57, (lmul, lmul, 0), (width, 1))
        if lmul <= 2:
            for ei, eew in enumerate(sew_values):
                if -3 <= lmul + ei - sew <= 3:
                    opcode = (0x26b58527 & ~(7 << 12)) | (memory_width_encoding[ei] << 12)
                    store(opcode, lmul, sew, eew, ei)

vectors = folder / 'matrix.hex'
vectors.write_text('\n'.join(packets) + '\n', encoding='ascii')
with Simulator() as sim:
    run, log = sim.run([ROOT / model['binary'], '+vectors=' + vectors.relative_to(ROOT).as_posix()],
                       folder / 'simulation.log', 600)
assert f'PASS rv_vector_integer_engine_tb instruction packets={len(packets)}' in log
assert sha(ROOT / model['binary']) == model['binary_sha256']
dump(folder / 'report.json', dict(
    passed=True, scope='Vector owner mixed source operand group decode in vl=0 configurations',
    model=model, generator_sha256=sha(__file__), packets=len(packets), by_family=by_family, vectors_sha256=sha(vectors), run=run))
print(f'PASS vector source group legality: {len(packets)} packets across {len(by_family)} forms', flush=True)

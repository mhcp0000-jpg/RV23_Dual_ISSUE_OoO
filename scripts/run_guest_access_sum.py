"""Exercise SPVP, PTE.U and host/guest SUM on explicit guest accesses."""

from itertools import product

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT


FOLDER = 'out/rva23/guest_access_sum'
BASE = 'sw/tests/rv64_hypervisor_gstage.S'
GVA = 0x400a0000
DATA = 0x765432108123fe80
STORE = 0x0123456789abcdef


def access_cases():
    for mode, user_page, spvp, vs_sum, hs_sum, op in product(
            ('M', 'HS'), range(2), range(2), (1, 0), (1, 0),
            ('hlv.d', 'hlvx.wu', 'hsv.d')):
        allowed = (not spvp or vs_sum) if user_page else spvp
        cause = 0 if allowed else (15 if op == 'hsv.d' else 13)
        yield mode, user_page, spvp, vs_sum, hs_sum, op, cause


def fixture():
    base = (ROOT / BASE).read_text(encoding='utf-8')
    setup = base.split('hs_entry:\n', 1)[0]
    enter_hs = setup.index('  la t0,hs_entry\n')
    lines = [setup[:enter_hs], 'la t0,m_trap', 'csrw mtvec,t0']
    previous_leaf = None
    for index, (mode, user_page, spvp, vs_sum, hs_sum, op, cause) in enumerate(access_cases(), 1):
        if (mode, user_page) != previous_leaf:
            if mode == 'HS' and user_page == 0:
                lines += ['la t0,fail', 'csrw mtvec,t0', setup[enter_hs:], 'hs_entry:']
            flags = 0xcf | (user_page << 4)
            lines += ['la t0,vslevel1', f'li t1,{(0x20000000 >> 2) | flags:#x}',
                      'sd t1,0(t0)', 'hfence.vvma']
            previous_leaf = mode, user_page
        # Keep the translation live across SPVP and SUM changes.
        lines += [f'li s7,{index}', f'li s0,{GVA:#x}', 'li s8,0x800a0000',
                  f'li t0,{DATA:#x}', 'sd t0,0(s8)', 'li t0,0x40000', 'csrc sstatus,t0']
        if hs_sum:
            lines.append('csrs sstatus,t0')
        lines += [f'li t0,{vs_sum << 18:#x}', 'csrw vsstatus,t0',
                  f'li t0,{spvp << 8:#x}', 'csrw hstatus,t0', f'li s1,{cause}',
                  'li s3,0', f'la s4,probe_{index}', f'li a2,{STORE:#x}', f'probe_{index}:',
                  f'{op} a2,(s0)', 'bne s3,s1,fail']
        register = STORE if cause or op == 'hsv.d' else DATA if op == 'hlv.d' else DATA & 0xffffffff
        memory = STORE if not cause and op == 'hsv.d' else DATA
        lines += [f'li t0,{register:#x}', 'bne a2,t0,fail',
                  'ld t1,0(s8)', f'li t2,{memory:#x}', 'bne t1,t2,fail']
    lines += ['li t1,1', 'j finish']
    for prefix, guest_metadata, status in (
            ('m', 'mtval2', ['csrr t1,mstatus', 'srli t1,t1,38', 'andi t1,t1,3']),
            ('s', 'htval', ['csrr t1,hstatus', 'srli t1,t1,6', 'andi t1,t1,1'])):
        label = 'm_trap' if prefix == 'm' else 'hs_trap'
        lines += [label + ':', 'beqz s1,fail',
                  f'csrr s3,{prefix}cause', 'bne s3,s1,fail',
                  f'csrr t0,{prefix}epc', 'bne t0,s4,fail',
                  f'csrr t1,{prefix}tval', 'bne t1,s0,fail',
                  f'csrr t1,{guest_metadata}', 'bnez t1,fail',
                  *status, 'li t2,1', 'bne t1,t2,fail',
                  'addi t0,t0,4', f'csrw {prefix}epc,t0', f'{prefix}ret']
    lines += ['fail:', 'slli t1,s7,1', 'ori t1,t1,3',
              'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'stop: j stop',
              '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
              'tohost: .dword 0', 'fromhost: .dword 0', base[base.index('.section .bss'):]]
    return '\n'.join(lines) + '\n'


def verify_traces(sail_trace, rtl_trace):
    rtl = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), rtl)
    assert mismatch is None, mismatch
    probes = {'hlv.d': 0x6c044673, 'hlvx.wu': 0x68344673, 'hsv.d': 0x6ec44073}
    expected = [(probes[op], cause) for _, _, _, _, _, op, cause in access_cases()]
    observed = []
    for row in rtl:
        word = int(row['instruction'], 16)
        if int(row['pc'], 16) < 0x80000000:
            continue
        if row['trap'] == '1':
            assert word in probes.values() and int(row['tval'], 16) == GVA and row['rd_write'] == '0'
            observed.append((word, int(row['cause'])))
        elif word in probes.values():
            observed.append((word, 0))
    assert observed == expected, observed
    return dict(accesses=len(observed), load_faults=sum(cause == 13 for _, cause in observed),
                store_faults=sum(cause == 15 for _, cause in observed), matched_events=events)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'test.S'
    source.write_text(fixture(), encoding='utf-8')
    outcomes = run_fixture(source, folder, __file__, verify_traces,
                           source_dependencies=(BASE,), timeout_cycles=300000)
    print('PASS native HLV/HLVX/HSV SUM and SPVP', outcomes, flush=True)


if __name__ == '__main__':
    main()

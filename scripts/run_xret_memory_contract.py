"""Replay MRET/SRET privilege restoration with translated data witnesses."""

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT


FOLDER = 'out/rva23/xret_memory_contract'
MPRV = 1 << 17
MPV = 1 << 39
TARGETS = {
    'M': (3, 0, 11, 0x80004000, 22, 'm_target'),
    'HS': (1, 0, 9, 0x80003000, 11, 's_target'),
    'U': (0, 0, 8, 0x80004000, 22, 'u_target'),
    'VS': (1, 1, 10, 0x80003000, 33, 's_target'),
    'VU': (0, 1, 8, 0x80004000, 44, 'u_target'),
}
CASES = ([('mret', 'M', name) for name in TARGETS]
         + [('sret', 'M', name) for name in ('HS', 'U', 'VS', 'VU')]
         + [('sret', 'HS', name) for name in ('HS', 'U')]
         + [('sret', 'VS', name) for name in ('VS', 'VU')])


def install_tables():
    lines = []
    for name, data in [('hs', (0x800a0000, 0x800a1000)), ('vs', (0x800a2000, 0x800a3000))]:
        for parent, child, offset in [('root', 'mid', 16), ('mid', 'leaf', 0)]:
            lines += [f'la t0,{name}_{parent}', f'la t1,{name}_{child}',
                      'srli t1,t1,2', 'ori t1,t1,1', f'sd t1,{offset}(t0)']
        lines.append(f'la t0,{name}_leaf')
        for slot, address, flags in [(0, 0x80000000, 0x4b), (1, 0x80001000, 0x5b),
                                      (3, data[0], 0xc7), (4, data[1], 0xd7)]:
            lines += [f'li t1,{(address >> 2) | flags:#x}', f'sd t1,{8 * slot}(t0)']
        csr = 'satp' if name == 'hs' else 'vsatp'
        lines += [f'la t0,{name}_root', 'srli t0,t0,12', f'li t1,{1 << 63:#x}',
                  'or t0,t0,t1', f'csrw {csr},t0']
    for index, value in enumerate((11, 22, 33, 44)):
        lines += [f'li t0,{0x800a0000 + index * 4096:#x}', f'li t1,{value}', 'sd t1,0(t0)']
    return lines + ['sfence.vma', 'hfence.vvma']


def probe_loads(failure):
    return ['ld a0,0(s1)', f'bne a0,s2,{failure}', 'vsetivli zero,1,e64,m1,tu,mu',
            'vle64.v v8,(s1)', 'vmv.x.s a0,v8', f'bne a0,s2,{failure}']


def fixture():
    lines = [
        '.section .text.init,"ax"', '.option norvc', '.option norelax', '.globl _start',
        '_start:', 'la t0,m_trap', 'csrw mtvec,t0', 'csrw medeleg,zero',
        'li t0,-1', 'csrw pmpaddr0,t0', 'li t0,31', 'csrw pmpcfg0,t0',
        *install_tables(),
    ]
    for index, (operation, caller, target) in enumerate(CASES):
        priv, guest, cause, address, value, label = TARGETS[target]
        status = MPRV | (MPV * guest) | (priv << 11) | 0x200
        # Toggle SPIE by destination privilege and exercise SPP=0 and SPP=1.
        sstatus = (int(priv == 1) << 8) | (int(priv == 0) << 5) | 0x200
        # Hardware should preserve hstatus.SPV on MRET and on VS SRET.
        saved_spv = guest if operation == 'sret' and caller == 'M' else 1
        expected_spv = 0 if operation == 'sret' and caller != 'VS' else saved_spv
        lines += [
            f'case_{index}:', f'li s0,{cause}', f'li s1,{address:#x}', f'li s2,{value}',
            f'la s3,{label}_call', f'la s4,case_{index + 1}',
            f'li s5,{(priv << 11) | (guest * MPV) | (MPRV if target == "M" else 0):#x}',
            f'li s6,{expected_spv << 7:#x}', f'li s7,{sstatus:#x}',
            f'li t0,{saved_spv << 7:#x}', 'csrw hstatus,t0',
            'li t0,0x200', 'csrw vsstatus,t0', f'la a2,{label}',
        ]
        if operation == 'mret':
            lines += ['csrw mepc,a2', f'li t0,{(status | (MPV if target == "M" else 0)):#x}',
                      'csrw mstatus,t0', 'mret']
        elif caller == 'M':
            lines += ['csrw sepc,a2', f'li t0,{MPRV | sstatus:#x}', 'csrw mstatus,t0', 'sret']
        else:
            if caller == 'HS':
                lines.append('csrw hstatus,zero')
            lines += ['la t0,nested_return', 'csrw mepc,t0',
                      f'li t0,{MPRV | 0xa00 | (MPV if caller == "VS" else 0):#x}',
                      'csrw mstatus,t0', 'mret']
    lines += [
        f'case_{len(CASES)}:', 'li t1,1', 'j finish',
        'nested_return:', 'csrw sepc,a2', 'csrw sstatus,s7', 'sret',
        'm_target:', 'csrr t0,mstatus', f'li t1,{MPRV | MPV | 0x1800:#x}',
        'and t0,t0,t1', f'li t1,{MPRV:#x}', 'bne t0,t1,fail',
        *probe_loads('fail'), 'm_target_call:', 'ecall', 'j fail',
        's_target:', *probe_loads('fail'), 's_target_call:', 'ecall', 'j fail',
        'm_trap:', 'csrr t0,mcause', 'bne t0,s0,fail', 'csrr t0,mepc', 'bne t0,s3,fail',
        'csrr t0,mstatus', f'li t1,{MPRV | MPV | 0x1800:#x}', 'and t0,t0,t1',
        'bne t0,s5,fail', 'csrr t0,hstatus', 'andi t0,t0,128', 'bne t0,s6,fail', 'jr s4',
        'fail:', 'li t1,3', 'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt:j halt',
        '.balign 4096', 'u_target:', *probe_loads('user_fail'),
        'u_target_call:', 'ecall', 'user_fail:', 'j user_fail',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0', '.section .bss', '.balign 4096',
    ]
    for name in ('hs', 'vs'):
        lines.extend(f'{name}_{table}:.space 4096' for table in ('root', 'mid', 'leaf'))
    return '\n'.join(lines) + '\n'


def verify_traces(sail_trace, rtl_trace):
    actual = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), actual)
    assert mismatch is None, mismatch
    causes, scalar_loads, vector_loads = [], [], []
    mret = sret = 0
    for row in actual:
        word = int(row['instruction'], 16)
        if int(row['pc'], 16) < 0x80000000:
            continue
        if row['trap'] == '1':
            assert word == 0x73 and int(row['tval'], 16) == 0
            causes.append(int(row['cause']))
        elif word == 0x0004b503:  # ld a0,0(s1)
            scalar_loads.append(int(row['wdata'], 16))
        elif word == 0x42802557:  # vmv.x.s a0,v8 after vle64.v
            vector_loads.append(int(row['wdata'], 16))
        elif word == 0x30200073:
            mret += 1
        elif word == 0x10200073:
            sret += 1
    assert causes == [TARGETS[target][2] for _, _, target in CASES]
    assert scalar_loads == vector_loads == [TARGETS[target][4] for _, _, target in CASES]
    assert (mret, sret) == (9, 8)
    return dict(cases=len(CASES), mret=mret, sret=sret,
                scalar_loads=len(scalar_loads), vector_loads=len(vector_loads), matched_events=events)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'test.S'
    source.write_text(fixture(), encoding='utf-8')
    results = run_fixture(source, folder, __file__, verify_traces)
    print('PASS native xRET memory privilege contract', results, flush=True)


if __name__ == '__main__':
    main()

"""Check non-leaf PTE encodings at all stages of the native Sv39 walkers."""

from itertools import product

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT


FOLDER = 'out/rva23/pte_nonleaf_contract'
BASE = 'sw/tests/rv64_hypervisor_gstage.S'
GVA = 0x400a0000
DATA = 0x765432108123fe80
STORE = 0x0123456789abcdef
STAGES = ('S', 'VS', 'G-final', 'G-implicit')
RESERVED_BITS = (2, 4, 6, 7, *range(54, 64))
CONTROLS = (0, 0x20, 0x300, 0x320)  # G and RSW fields are legal on pointers.
PROBE_WORDS = {
    ('S', False): 0x00043603, ('S', True): 0x00c43023,
    ('H', False): 0x6c044673, ('H', True): 0x6ec44073,
}


def cases():
    for stage, flags, store in product(STAGES, CONTROLS + tuple(1 << bit for bit in RESERVED_BITS), (False, True)):
        guest_page_fault = stage.startswith('G-')
        cause = 0 if flags in CONTROLS else (21 if guest_page_fault else 13) + 2 * store
        guest_pa = {'G-final': 0x200a0000, 'G-implicit': 0x10000008}.get(stage, 0)
        yield dict(stage=stage, flags=flags, store=store, cause=cause,
                   htval=guest_pa >> 2, htinst=0x3000 if stage == 'G-implicit' else 0)


def stage_pointer(stage):
    return {
        'S': ['la s4,sroot', 'addi s4,s4,8', 'la s5,slevel1', 'srli s5,s5,2', 'ori s5,s5,1'],
        'VS': ['la s4,vsroot', 'addi s4,s4,8', 'li s5,0x4000401'],
        'G-final': ['la s4,glevel1', 'li t0,2048', 'add s4,s4,t0',
                    'la s5,gdata', 'srli s5,s5,2', 'ori s5,s5,1'],
        'G-implicit': ['la s4,glevel1', 'addi s4,s4,1024',
                       'la s5,gvsptes', 'srli s5,s5,2', 'ori s5,s5,1'],
    }[stage]


def fixture():
    base = (ROOT / BASE).read_text(encoding='utf-8')
    lines = [
        base.split('hs_entry:\n', 1)[0], 'hs_entry:',
        'li t0,0x100', 'csrw hstatus,t0', 'li t0,0x4000000000000000', 'csrw henvcfg,t0',
        f'li s0,{GVA:#x}', 'li s8,0x800a0000',
        # Identity-map the host, and give the S-stage probe its own pointer.
        'la t0,sroot', 'li t1,0x200000cf', 'sd t1,16(t0)',
        'la t0,slevel1', 'sd t1,0(t0)',
        'la t0,sroot', 'srli t0,t0,12', 'li t1,0x8000000000000000', 'or t0,t0,t1',
        'csrw satp,t0', 'sfence.vma',
        # The final G-stage data mapping can also walk through a non-leaf PTE.
        'la t0,gdata', 'li t1,0x200280df', 'sd t1,1280(t0)',
    ]
    previous_stage = None
    for index, case in enumerate(cases(), 1):
        stage, store, cause = case['stage'], case['store'], case['cause']
        if stage != previous_stage:
            lines.extend(stage_pointer(stage))
            previous_stage = stage
        fences = ['sfence.vma'] if stage == 'S' else ['hfence.gvma', 'hfence.vvma']
        if stage == 'S':
            instruction = 'sd a2,0(s0)' if store else 'ld a2,0(s0)'
        else:
            instruction = 'hsv.d a2,(s0)' if store else 'hlv.d a2,(s0)'
        lines += [
            f'li s7,{index}', f'li t0,{case["flags"]:#x}', 'or t0,t0,s5', 'sd t0,0(s4)',
            *fences, f'li t0,{DATA:#x}', 'sd t0,0(s8)',
            f'li a3,{int(stage != "S")}', f'li a4,{cause}',
            f'li a5,{case["htval"]:#x}', f'li a6,{case["htinst"]:#x}',
            f'la s6,probe_{index}', f'li a2,{STORE:#x}', 'li s3,0',
            f'probe_{index}: {instruction}', 'bne s3,a4,fail',
            f'li t0,{STORE if store or cause else DATA:#x}', 'bne a2,t0,fail',
            'ld t1,0(s8)', f'li t0,{STORE if store and not cause else DATA:#x}', 'bne t0,t1,fail',
            'sd s5,0(s4)', *fences,
        ]
    lines += [
        'li t1,1', 'j finish', 'hs_trap:', 'beqz a4,fail',
        'csrr s3,scause', 'bne s3,a4,fail', 'csrr t0,sepc', 'bne t0,s6,fail',
        'csrr t1,stval', 'bne t1,s0,fail', 'csrr t1,htval', 'bne t1,a5,fail',
        'csrr t1,htinst', 'bne t1,a6,fail', 'csrr t1,hstatus',
        'srli t1,t1,6', 'andi t1,t1,1', 'bne t1,a3,fail',
        'addi t0,t0,4', 'csrw sepc,t0', 'sret',
        'fail:', 'slli t1,s7,1', 'ori t1,t1,1', 'finish:', 'la t0,tohost',
        'sd t1,0(t0)', 'halt: j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost:.dword 0', 'fromhost:.dword 0', base[base.index('.section .bss'):],
        'sroot:.space 4096', 'slevel1:.space 4096', 'gdata:.space 4096',
    ]
    return '\n'.join(lines) + '\n'


def verify_traces(sail_trace, rtl_trace):
    rtl = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), rtl)
    assert mismatch is None, mismatch
    observed = []
    for row in rtl:
        word = int(row['instruction'], 16)
        if int(row['pc'], 16) < 0x80000000:
            continue
        if row['trap'] == '1':
            assert word in PROBE_WORDS.values() and int(row['tval'], 16) == GVA and row['rd_write'] == '0'
            observed.append((word, int(row['cause'])))
        elif word in PROBE_WORDS.values():
            observed.append((word, 0))
    expected = [(PROBE_WORDS['S' if case['stage'] == 'S' else 'H', case['store']], case['cause'])
                for case in cases()]
    assert observed == expected, observed
    return dict(accesses=len(observed), faulting_accesses=sum(cause != 0 for _, cause in observed),
                matched_events=events)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'test.S'
    source.write_text(fixture(), encoding='utf-8')
    results = run_fixture(source, folder, __file__, verify_traces, source_dependencies=(BASE,),
                          timeout_cycles=500000)
    print('PASS native Sv39 non-leaf PTE contract', results, flush=True)


if __name__ == '__main__':
    main()

"""Exercise 64 KiB NAPOT translations and reserved encodings on the H/V SoC."""

from run_hv_sail_fixture import run_fixture
from run_sail_event_comparison import compare, read_csv
from sim_runner import ROOT


FOLDER = 'out/rva23/svnapot_contract'
BASE = 'sw/tests/rv64_hypervisor_gstage.S'
VA = 0x400a0000
GPA = 0x200a0000
PA = 0x800a0000
REMAPPED_PA = 0x800b0000
N = 1 << 63
STAGES = ('S', 'VS', 'G', 'VS+G')
FETCHES = ((0x10, 37), (0xf010, 53))
PROBES = {
    ('S', False): 0x00043603, ('S', True): 0x00c43023,
    ('H', False): 0x6c044673, ('H', True): 0x6ec44073,
}


def region_updates(stage):
    yield 8, PA, tuple(range(16))
    if stage == 'VS+G':
        yield 8, REMAPPED_PA, tuple(range(16))
    else:
        for encoding in range(16):
            if encoding != 8:
                yield encoding, PA, (encoding,)


def install_pointer(parent, offset, child):
    return [f'la t0,{parent}', f'la t1,{child}', 'srli t1,t1,2', 'ori t1,t1,1',
            f'sd t1,{offset}(t0)']


def set_mapping(stage):
    if stage == 'S':
        return [*install_pointer('sroot', 8, 'smid'), *install_pointer('smid', 0, 'sdata'),
                'la t0,sroot', 'li t1,0x200000cf', 'sd t1,16(t0)',
                'srli t0,t0,12', f'li t1,{N:#x}', 'or t0,t0,t1', 'csrw satp,t0', 'sfence.vma']
    # Reset both normal mappings when switching stages, then install the
    # page-table pointers needed for this combination.
    lines = ['la t0,vslevel1', 'li t1,0x080000cf', 'sd t1,0(t0)',
             'la t0,glevel1', 'li t2,2048', 'add t0,t0,t2', 'li t1,0x200000df', 'sd t1,0(t0)']
    if stage in ('VS', 'VS+G'):
        lines += ['la t0,vslevel1', 'li t1,0x04000801', 'sd t1,0(t0)']
    if stage in ('G', 'VS+G'):
        lines += ['la t0,glevel1', 'li t2,2048', 'add t0,t0,t2',
                  'la t1,gdata', 'srli t1,t1,2', 'ori t1,t1,1', 'sd t1,0(t0)']
    return lines + ['hfence.gvma', 'hfence.vvma']


def region_entries(stage, encoding, physical, update):
    tables = {'S': [('sdata', physical, 0xcf)],
              'VS': [('vsdata', GPA, 0xc7)],
              'G': [('gdata', physical, 0xd7)],
              'VS+G': [('vsdata', GPA, 0xc7), ('gdata', physical, 0xd7)]}
    lines = []
    for table, output, flags in tables[stage]:
        pte = N | (output >> 2) | (encoding << 10) | flags
        label = f'fill_{table}_{update}'
        lines += [f'la t0,{table}', 'addi t0,t0,1280', f'li t1,{pte:#x}', 'li t2,16',
                  label + ':', 'sd t1,0(t0)', 'addi t0,t0,8', 'addi t2,t2,-1', f'bnez t2,{label}']
    return lines + (['sfence.vma'] if stage == 'S' else ['hfence.gvma', 'hfence.vvma'])


def fixture():
    base = (ROOT / BASE).read_text(encoding='utf-8')
    lines = [
        base.split('hs_entry:\n', 1)[0], 'hs_entry:', 'li t0,0x100', 'csrw hstatus,t0',
        'la t0,gvsptes', 'la t1,vsdata', 'srli t1,t1,2', 'ori t1,t1,0x53', 'sd t1,16(t0)',
    ]
    update = 0
    for stage in STAGES:
        lines.extend(set_mapping(stage))
        ordinary = stage == 'S'
        load = 'ld a2,0(s0)' if ordinary else 'hlv.d a2,(s0)'
        store = 'sd a2,0(s0)' if ordinary else 'hsv.d a2,(s0)'
        for encoding, physical, pages in region_updates(stage):
            update += 1
            lines.extend(region_entries(stage, encoding, physical, update))
            for page in pages:
                value = 0x100 * update + page
                suffix = f'{update}_{page}'
                fault = 0 if encoding == 8 else 21 if stage == 'G' else 13
                offset = page * 4096 + 0x38
                lines += [
                    f'li s0,{VA + offset:#x}', f'li s8,{physical + offset:#x}',
                    f'li t0,{value}', 'sd t0,0(s8)',
                    f'li a3,{int(not ordinary)}', f'li s5,{(GPA + offset) >> 2 if fault == 21 else 0:#x}',
                    f'li a4,{fault}', 'li a2,7', 'li s3,0', f'la s6,load_{suffix}',
                    f'load_{suffix}: {load}', 'bne s3,a4,fail',
                    f'li t0,{7 if fault else value}', 'bne a2,t0,fail',
                    'li a2,9', 'li s3,0', f'li a4,{fault + 2 if fault else 0}', f'la s6,store_{suffix}',
                    f'store_{suffix}: {store}', 'bne s3,a4,fail', 'ld t0,0(s8)',
                    f'li t1,{value if fault else 9}', 'bne t0,t1,fail',
                ]
            if stage == 'S' and encoding == 8:
                lines += [
                    f'li t0,{PA + 4096 - 8:#x}', 'li t1,71', 'sd t1,0(t0)', 'li t1,83', 'sd t1,8(t0)',
                    f'li t0,{VA + 4096 - 8:#x}', 'vsetivli zero,2,e64,m1,tu,mu',
                    'vle64.v v8,(t0)', 'vmv.x.s t1,v8', 'li t2,71', 'bne t1,t2,fail',
                    'vslidedown.vi v9,v8,1', 'vmv.x.s t1,v9', 'li t2,83', 'bne t1,t2,fail',
                ]
                for offset, result in FETCHES:
                    lines += [f'li t0,{PA + offset:#x}', f'li t1,{(result << 20) | 0x513:#x}',
                              'sw t1,0(t0)', 'li t1,0x8067', 'sw t1,4(t0)']
                lines.append('fence.i')
                for offset, result in FETCHES:
                    lines += [f'li t0,{VA + offset:#x}', 'jalr ra,t0,0',
                              f'li t1,{result}', 'bne a0,t1,fail']
    lines += [
        'li t1,1', 'j finish', 'hs_trap:', 'beqz a4,fail',
        'csrr s3,scause', 'bne s3,a4,fail', 'csrr t0,sepc', 'bne t0,s6,fail',
        'csrr t1,stval', 'bne t1,s0,fail', 'csrr t1,htval', 'bne t1,s5,fail',
        'csrr t1,htinst', 'bnez t1,fail', 'csrr t1,hstatus',
        'srli t1,t1,6', 'andi t1,t1,1', 'bne t1,a3,fail',
        'addi t0,t0,4', 'csrw sepc,t0', 'sret',
        'fail:', 'li t1,3', 'finish:', 'la t0,tohost', 'sd t1,0(t0)', 'halt: j halt',
        '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
        'tohost: .dword 0', 'fromhost: .dword 0', base[base.index('.section .bss'):],
        'sroot:.space 4096', 'smid:.space 4096', 'sdata:.space 4096',
        'vsdata:.space 4096', 'gdata:.space 4096',
    ]
    return '\n'.join(lines) + '\n'


def verify_traces(sail_trace, rtl_trace):
    rtl = read_csv(rtl_trace)
    events, mismatch = compare(read_csv(sail_trace), rtl)
    assert mismatch is None, mismatch
    observed = []
    fetches = []
    vector_reads = 0
    for row in rtl:
        pc, word = int(row['pc'], 16), int(row['instruction'], 16)
        if any(pc == VA + offset for offset, _ in FETCHES):
            assert row['trap'] == '0' and row['rd_write'] == '1' and int(row['rd']) == 10
            fetches.append((pc - VA, int(row['wdata'], 16)))
        if pc < 0x80000000:
            continue
        if row['trap'] == '1':
            assert word in PROBES.values() and row['rd_write'] == '0'
            observed.append((word, int(row['cause']), int(row['tval'], 16)))
        elif word in PROBES.values():
            observed.append((word, 0, 0))
        elif word == 0x0202f407:  # vle64.v v8,(t0)
            vector_reads += 1
    expected = []
    for stage in STAGES:
        for encoding, _, pages in region_updates(stage):
            for page in pages:
                for store in (False, True):
                    word = PROBES['S' if stage == 'S' else 'H', store]
                    cause = 0 if encoding == 8 else (21 if stage == 'G' else 13) + 2 * store
                    expected.append((word, cause, VA + 4096 * page + 0x38 if cause else 0))
    assert observed == expected and vector_reads == 1 and tuple(fetches) == FETCHES
    return dict(accesses=len(observed), reserved_encoding_faults=sum(cause != 0 for _, cause, _ in observed),
                vector_cross_page_loads=vector_reads, instruction_fetches=len(fetches), matched_events=events)


def main():
    folder = ROOT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'test.S'
    source.write_text(fixture(), encoding='utf-8')
    results = run_fixture(source, folder, __file__, verify_traces, source_dependencies=(BASE,),
                          timeout_cycles=600000)
    print('PASS native Svnapot mapping and reserved encodings', results, flush=True)


if __name__ == '__main__':
    main()

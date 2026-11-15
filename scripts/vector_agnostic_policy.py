"""Element-level oracle for the four operations in vector-state fixtures.

V 1.0 permits an agnostic element to preserve its old value or become all ones.
Prestart elements and every destination element when VL=0 remain unchanged.
No mask-result instructions are in these fixtures (their tail rules differ).
"""
from collections import Counter

INITIAL=bytes((i*37+(i//16)*13+0xaa)&255 for i in range(512))


def snapshots(rows,load_pc):
    values=[int(r['wdata'],16) for r in rows if int(r['pc'],16)==load_pc]
    if len(values)!=320:
        raise ValueError(f'Expected 320 snapshot words, got {len(values)}')
    return [b''.join(v.to_bytes(8,'little') for v in values[i:i+64]) for i in range(0,320,64)]


def validate_transition(case,stage,old,new):
    if len(old)!=512 or len(new)!=512 or stage not in [1,2,3,4]:
        raise ValueError('Invalid snapshot geometry/stage')
    width=case['sew']//8
    registers=1 if case['lmul'].startswith('mf') else int(case['lmul'][1:])
    start,end=128,128+16*registers # destination v8 and its physical group
    if old[:start]!=new[:start] or old[end:]!=new[end:]:
        raise ValueError(f'stage={stage} outside_destination')
    counts=Counter()
    if stage==3:
        if old!=new:
            raise ValueError('stage=3 vl_zero')
        return {'vl_zero':(end-start)//width}
    vl=case['vlmax']-1 if stage==2 else case['vlmax']
    vstart=0 if stage==2 else 1
    all_ones=(1<<case['sew'])-1

    def element(data,base,index):
        return int.from_bytes(data[base+index*width:base+(index+1)*width],'little')

    for index in range((end-start)//width):
        before=element(old,start,index)
        actual=element(new,start,index)
        if index<vstart:
            category,allowed='prestart',{before}
        elif index>=vl:
            category='tail_agnostic' if case['ta'] else 'tail_undisturbed'
            allowed={before,all_ones} if case['ta'] else {before}
        elif stage==1 and not ((INITIAL[index//8]>>(index%8))&1):
            category='mask_agnostic' if case['ma'] else 'mask_undisturbed'
            allowed={before,all_ones} if case['ma'] else {before}
        else:
            category='active'
            source=element(INITIAL,256,index)
            other=element(INITIAL,384,index)
            if stage==1:
                expected=(source+other)&all_ones
            elif stage==2:
                expected=all_ones # unsigned source + scalar all-ones, saturating
            else:
                expected=0 if other>=case['vlmax'] else element(INITIAL,256,other)
            allowed={expected}
        if actual not in allowed:
            raise ValueError(f'stage={stage} {category} element={index} got={actual:x} allowed={sorted(allowed)}')
        counts[category]+=1
    return dict(counts)


def validate(case,states):
    if len(states)!=5 or states[0]!=INITIAL:
        raise ValueError('Initial full-register snapshot differs from fixture')
    counts=Counter()
    for stage in [1,2,3,4]:
        counts.update(validate_transition(case,stage,states[stage-1],states[stage]))
    return dict(counts)


def compare_snapshots(reference,actual,load_pc,normalize):
    """Call only after both complete snapshot sequences pass validate()."""
    start=next(i for i,r in enumerate(actual) if int(r['pc'],16)==int(reference[0]['pc'],16))
    differences=0
    for index,left in enumerate(reference):
        right=actual[start+index] if start+index<len(actual) else None
        if right is None:
            raise ValueError(f'Trace ended at event {index}')
        a,b=normalize(left),normalize(right)
        if a==b:
            continue
        if a['pc']==b['pc']==load_pc and a['writeback'] and b['writeback']:
            a['writeback']=a['writeback'][:2]
            b['writeback']=b['writeback'][:2]
            if a==b:
                differences+=1
                continue
        raise ValueError(f'Non-snapshot trace mismatch event={index} Sail={left} RTL={right}')
    return len(reference),differences

"""Exact vector-element interpretation, including mixed integer widths and ROD."""
from fp_reference import BinaryFP,RTZ,NX,NV

class VectorFP(BinaryFP):
    def pack(self,value,rm,negative_zero=False):
        if rm!=6:return super().pack(value,rm,negative_zero)
        result,flags=super().pack(value,RTZ,negative_zero)
        return result|int(bool(flags&NX)),flags

formats={1:VectorFP(5,10),2:VectorFP(8,23),3:VectorFP(11,52)}
MASK=(1<<64)-1
def boxed(value,size):return value|((MASK>>(8<<size))<<(8<<size))

def interpret(name,insn,sew,rm,a,b,c,mask,estimates):
    family=insn>>26;selector=(insn>>15)&31;scalar=(insn>>12)&7==5
    if rm>4:return 0,0,True
    conversion=family==0x12
    if conversion:
        wide=bool(selector&8) and not selector&16;narrow=bool(selector&16);kind=selector&7
        if sew<1 or ((wide or narrow) and sew==3):return 0,0,True
        src=sew+int(narrow);dst=sew+int(wide)
        r=1 if kind in [6,7] else (6 if kind==5 else rm)
        if kind in [4,5]:
            if min(src,dst)==1 and name not in ['vfwcvt.f.f.v','vfncvt.f.f.w']:return 0,0,True
            result,flags=formats[dst].convert(a&formats[src].mask,formats[src],r)
        elif kind in [0,1,6,7]:
            if src<2:return 0,0,True
            result,flags=formats[src].to_int(a&formats[src].mask,8<<dst,not kind&1,r)
            result&=(1<<(8<<dst))-1
        else:
            if dst<2:return 0,0,True
            result,flags=formats[dst].from_int(a,8<<src,not kind&1,r)
        return result,flags,False
    if sew<2 or (family>=0x30 and sew!=2):return 0,0,True
    f=formats[sew];aa=a&f.mask
    if scalar and sew==2 and b>>32!=0xffffffff:b=f.nan
    bb=b&f.mask;cc=c&f.mask;pre_flags=0
    reduction=(insn>>12)&7==1 and family in [1,3,5,7,0x31,0x33]
    if family>=0x30:
        narrow=f;f=formats[3]
        aa=a if family in [0x34,0x36] else f.convert(aa,narrow,0)[0]
        if family not in [0x34,0x36]:pre_flags|=NV if narrow.is_snan(a&narrow.mask) else 0
        bb=b if reduction else f.convert(bb,narrow,0)[0]
        if not reduction:pre_flags|=NV if narrow.is_snan(b&narrow.mask) else 0
        cc=c
    if family in [0,1,3,0x30,0x31,0x33,0x34]:value,flags=f.add(aa,bb,rm)
    elif family in [2,0x32,0x36]:value,flags=f.add(aa,bb,rm,True)
    elif family in [4,5,6,7]:value,flags=f.minmax(aa,bb,family in [6,7])
    elif family in [8,9,10]:
        sign=bb&f.signbit
        if family==9:sign^=f.signbit
        if family==10:sign^=aa&f.signbit
        value=(aa&~f.signbit)|sign;flags=0
    elif family in [14,15]:value=bb;flags=0
    elif family==16:
        value=boxed(aa,sew) if name=='vfmv.f.s' else bb;flags=0
    elif family==23:value=bb if insn&(1<<25) or mask else aa;flags=0
    elif family==19:
        if selector==0:value,flags=f.sqrt(aa,rm)
        elif selector in [4,5]:value,flags=estimates[(f.width,int(selector==4),rm,aa)]
        else:value,flags=f.classify(aa),0
    elif family in [24,25,27,28,29,31]:
        compare={24:'eq',25:'le',27:'lt',28:'eq',29:'lt',31:'le'}[family]
        value,flags=f.compare(bb,aa,compare) if family in [29,31] else f.compare(aa,bb,compare)
        if family==28:value=int(not value)
    elif family in [0x20,0x21]:value,flags=f.divide(bb,aa,rm) if family==0x21 else f.divide(aa,bb,rm)
    elif family in [0x24,0x38]:value,flags=f.multiply(aa,bb,rm)
    elif family==0x27:value,flags=f.add(bb,aa,rm,True)
    elif family in list(range(0x28,0x30))+list(range(0x3c,0x40)):
        # Floating MADD names overwrite the multiplicand, MACC the addend.
        mul2,addend=(aa,cc) if family&4 else (cc,aa)
        value,flags=f.fused(bb,mul2,addend,rm,bool(family&1),bool((family&3) in [1,2]))
    else:raise AssertionError(name)
    return value,flags|pre_flags,False

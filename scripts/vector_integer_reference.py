"""Unbounded-integer reference for one RVV integer/fixed-point element.

Register groups, masking, restart, memory and floating point are outside this
component. Inputs follow vs2 (a), vs1/scalar (b), old vd (c) ordering.
"""
def signed(x,n):
    x&=(1<<n)-1
    return x-(1<<n) if x>>(n-1) else x

def rounded(x,shift,rm):
    if shift==0:return x
    q,rem=divmod(x,1<<shift)
    if rm==0:up=rem>=(1<<(shift-1))
    elif rm==1:up=rem>(1<<(shift-1)) or (rem==(1<<(shift-1)) and q&1)
    elif rm==2:up=False
    else:up=rem!=0 and not q&1
    return q+up

def calculate(op,width,a,b,c,carry,wide,rm,ext):
    mask=(1<<width)-1;wide_mask=(1<<(2*width))-1
    aa=a&mask;bb=b&mask;sa=signed(a,width);sb=signed(b,width)
    wa=a&wide_mask;swa=signed(a,2*width)
    sh=b&(width-1);wsh=b&(2*width-1)
    bits=width;clip=None;value=0;saturation=False
    aliases={'vredsum':'vadd','vredand':'vand','vredor':'vor','vredxor':'vxor',
        'vredmin':'vmin','vredminu':'vminu','vredmax':'vmax','vredmaxu':'vmaxu',
        'vmand':'vand','vmor':'vor','vmxor':'vxor','vmandn':'vandn'}
    op=aliases.get(op,op)
    if op=='vadd':value=aa+bb
    elif op=='vsub':value=aa-bb
    elif op=='vrsub':value=bb-aa
    elif op=='vminu':value=min(aa,bb)
    elif op=='vmin':value=min(sa,sb)
    elif op=='vmaxu':value=max(aa,bb)
    elif op=='vmax':value=max(sa,sb)
    elif op=='vand':value=aa&bb
    elif op=='vor':value=aa|bb
    elif op=='vxor':value=aa^bb
    elif op=='vandn':value=aa&~bb
    elif op=='vmorn':value=aa|~bb
    elif op=='vmnand':value=~(aa&bb)
    elif op=='vmnor':value=~(aa|bb)
    elif op=='vmxnor':value=~(aa^bb)
    elif op=='vadc':value=aa+bb+carry
    elif op=='vmadc':value=(aa+bb+carry)>>width
    elif op=='vsbc':value=aa-bb-carry
    elif op=='vmsbc':value=aa<bb+carry
    elif op=='vmerge':value=bb if carry else aa
    elif op=='vmv':value=bb
    elif op=='vmseq':value=aa==bb
    elif op=='vmsne':value=aa!=bb
    elif op=='vmsltu':value=aa<bb
    elif op=='vmslt':value=sa<sb
    elif op=='vmsleu':value=aa<=bb
    elif op=='vmsle':value=sa<=sb
    elif op=='vmsgtu':value=aa>bb
    elif op=='vmsgt':value=sa>sb
    elif op=='vsaddu':value=aa+bb;clip='u'
    elif op=='vsadd':value=sa+sb;clip='s'
    elif op=='vssubu':value=aa-bb;clip='u'
    elif op=='vssub':value=sa-sb;clip='s'
    elif op=='vsll':value=aa<<sh
    elif op=='vsrl':value=aa>>sh
    elif op=='vsra':value=sa>>sh
    elif op=='vssrl':value=rounded(aa,sh,rm)
    elif op=='vssra':value=rounded(sa,sh,rm)
    elif op=='vnsrl':value=wa>>wsh
    elif op=='vnsra':value=swa>>wsh
    elif op=='vnclipu':value=rounded(wa,wsh,rm);clip='u'
    elif op=='vnclip':value=rounded(swa,wsh,rm);clip='s'
    elif op=='vaaddu':value=rounded(aa+bb,1,rm)
    elif op=='vaadd':value=rounded(sa+sb,1,rm)
    elif op=='vasubu':value=rounded(aa-bb,1,rm)
    elif op=='vasub':value=rounded(sa-sb,1,rm)
    elif op=='vsmul':value=rounded(sa*sb,width-1,rm);clip='s'
    elif op=='vdivu':value=mask if bb==0 else aa//bb
    elif op in ['vdiv','vrem']:
        q=0 if sb==0 else (abs(sa)//abs(sb))*(-1 if (sa<0)!=(sb<0) else 1)
        value=(mask if sb==0 else q) if op=='vdiv' else (sa if sb==0 else sa-q*sb)
    elif op=='vremu':value=aa if bb==0 else aa%bb
    elif op=='vmul':value=aa*bb
    elif op=='vmulhu':value=(aa*bb)>>width
    elif op=='vmulhsu':value=(sa*bb)>>width
    elif op=='vmulh':value=(sa*sb)>>width
    elif op=='vmacc':value=c+aa*bb
    elif op=='vnmsac':value=c-aa*bb
    elif op=='vmadd':value=aa+bb*c
    elif op=='vnmsub':value=aa-bb*c
    elif op=='vwmulu':value=aa*bb;bits*=2
    elif op=='vwmulsu':value=sa*bb;bits*=2
    elif op=='vwmul':value=sa*sb;bits*=2
    elif op=='vwmaccu':value=c+aa*bb;bits*=2
    elif op=='vwmacc':value=c+sa*sb;bits*=2
    elif op=='vwmaccsu':value=c+aa*sb;bits*=2
    elif op=='vwmaccus':value=c+sa*bb;bits*=2
    elif op=='vwaddu':value=(wa if wide else aa)+bb;bits*=2
    elif op=='vwadd':value=(swa if wide else sa)+sb;bits*=2
    elif op=='vwsubu':value=(wa if wide else aa)-bb;bits*=2
    elif op=='vwsub':value=(swa if wide else sa)-sb;bits*=2
    elif op=='vwredsumu':value=c+aa;bits*=2
    elif op=='vwredsum':value=c+sa;bits*=2
    elif op in ['vzext','vsext']:
        n=width>>ext
        if n<8 or ext==0:return 0,False,False
        value=a&((1<<n)-1) if op=='vzext' else signed(a,n)
    elif op=='vbrev':value=int(f'{aa:0{width}b}'[::-1],2)
    elif op=='vbrev8':value=int.from_bytes(bytes(int(f'{x:08b}'[::-1],2) for x in aa.to_bytes(width//8,'little')),'little')
    elif op=='vrev8':value=int.from_bytes(aa.to_bytes(width//8,'little'),'big')
    elif op=='vclz':value=width-aa.bit_length()
    elif op=='vctz':value=width if aa==0 else (aa&-aa).bit_length()-1
    elif op=='vcpop':value=aa.bit_count()
    elif op=='vrol':value=(aa<<sh)|(aa>>(width-sh))
    elif op=='vror':value=(aa>>sh)|(aa<<(width-sh))
    elif op=='vwsll':value=aa<<wsh;bits*=2
    else:return 0,False,False
    if width==64 and (bits==128 or op in ['vnsrl','vnsra','vnclipu','vnclip']):return 0,False,False
    if clip:
        lo,hi=(0,mask) if clip=='u' else (-(1<<(width-1)),(1<<(width-1))-1)
        saturation=not lo<=value<=hi;value=max(lo,min(hi,value))
    return value&((1<<bits)-1),saturation,True

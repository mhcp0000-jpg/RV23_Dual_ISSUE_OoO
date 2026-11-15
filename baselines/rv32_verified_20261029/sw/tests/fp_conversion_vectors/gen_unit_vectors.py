"""Actual FPU unit vectors: both widths, all legal kinds/rm and static/dynamic.

Inputs reuse the immutable1204-vector corpus. Exact Fraction arithmetic;
the existing C oracle remains unchanged. No DUT helper or host FP casts.
"""
import argparse,hashlib,json,re
from fractions import Fraction
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--header',type=Path,default=Path('out/fp_conversion_vectors/vectors.h'))
parser.add_argument('--output',type=Path,default=Path('out/fp_fcvt_unit_vectors'))
args=parser.parse_args()
source=args.header
metadata=json.loads((source.parent/'vectors.json').read_text(encoding='utf-8-sig'))
assert sha(source)==metadata['headerSha256']
inputs=sorted({int(v,16) for v in re.findall(r'^ \{0x([0-9a-f]{8})u,',source.read_text(encoding='utf-8'),re.M)})
assert len(inputs)==1204
out=args.output;assert not out.exists(),'Preserve previous vectors';out.mkdir(parents=True)

def oracle(bits,kind,rm,xlen):
    width=64 if kind&2 else 32;unsigned=bool(kind&1)
    sign=bool(bits>>31);exponent=(bits>>23)&255;fraction=bits&0x7fffff
    minimum,maximum=(0,(1<<width)-1) if unsigned else (-(1<<(width-1)),(1<<(width-1))-1)
    if exponent==255:
        value=maximum if fraction or not sign else minimum;flags=16
    else:
        mantissa=fraction if exponent==0 else (1<<23)|fraction
        exponent=-149 if exponent==0 else exponent-150
        rational=Fraction(mantissa<<exponent) if exponent>=0 else Fraction(mantissa,1<<-exponent)
        base,remainder=divmod(rational.numerator,rational.denominator)
        denominator=rational.denominator
        increment=(2*remainder>denominator or (2*remainder==denominator and base%2==1)) if rm==0 else (
          False if rm==1 else (sign and remainder!=0) if rm==2 else
          (not sign and remainder!=0) if rm==3 else 2*remainder>=denominator)
        value=-(base+int(increment)) if sign else base+int(increment)
        if value<minimum:value=minimum;flags=16
        elif value>maximum:value=maximum;flags=16
        else:flags=int(remainder!=0)
    value&=(1<<width)-1
    # Both W and WU word results are sign-extended on the wider integer port.
    if width==32 and value&(1<<31):value|=((1<<64)-1)^((1<<32)-1)
    return value&((1<<xlen)-1),flags

directed=[(0xdf000000,2,0,64,(0x8000000000000000,0)),
          (0x5f000000,2,0,64,(0x7fffffffffffffff,16)),
          (0x5f800000,3,0,64,(0xffffffffffffffff,16)),
          (0x4f000000,1,0,64,(0xffffffff80000000,0)),
          (0xbf000000,3,1,64,(0,1)),(0xbf000000,3,2,64,(0,16))]
for bits,kind,rm,xlen,expected in directed:assert oracle(bits,kind,rm,xlen)==expected
r=dict(scope=__doc__,inputHeaderSha256=sha(source),generatorSha256=sha(__file__),directedOracleChecks=len(directed),cases=[])
for xlen in (32,64):
    path=out/f'x{xlen}.hex';count=0
    with path.open('w',encoding='ascii') as stream:
        for bits in inputs:
            for kind in range(2 if xlen==32 else 4):
                for rm in range(5):
                    data,flags=oracle(bits,kind,rm,xlen)
                    for dynamic in (False,True):
                        encoded=7 if dynamic else rm
                        packed=bits
                        for width,value in [(2,kind),(3,encoded),(3,rm),(64,data),(5,flags)]:
                            assert 0<=value<1<<width;packed=(packed<<width)|value
                        assert packed.bit_length()<=109
                        stream.write(f'{packed:028x}\n');count+=1
    assert count==(24080 if xlen==32 else 48160)
    r['cases'].append(dict(xlen=xlen,count=count,file=str(path),sha256=sha(path)))
(out/'report.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
print('Generated actual FPU packets32=24080,64=48160, total72240',flush=True)

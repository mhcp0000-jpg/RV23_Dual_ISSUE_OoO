"""Exact parameterized IEEE binary oracle; no host floating-point arithmetic."""
from fractions import Fraction
from math import isqrt
RNE,RTZ,RDN,RUP,RMM=range(5)
NX,UF,OF,DZ,NV=1,2,4,8,16

def log2floor(value):
    n,d=value.numerator,value.denominator
    e=n.bit_length()-d.bit_length()
    if (n<(d<<e)) if e>=0 else ((n<<-e)<d):e-=1
    return e

def ratio(value,power):
    return (value.numerator,value.denominator<<power) if power>=0 else (value.numerator<<-power,value.denominator)

def round_int(n,d,negative,rm):
    q,r=divmod(n,d)
    if not r:return q,False
    increment=[2*r>d or (2*r==d and q&1),False,negative,not negative,2*r>=d][rm]
    return q+int(increment),True

class BinaryFP:
    def __init__(self,exponent_bits,fraction_bits):
        self.eb=exponent_bits;self.fb=fraction_bits;self.width=1+self.eb+self.fb
        self.signbit=1<<(self.width-1);self.fracmask=(1<<self.fb)-1
        self.expmax=(1<<self.eb)-1;self.bias=(1<<(self.eb-1))-1
        self.emin=1-self.bias;self.emax=self.bias
        self.inf=self.expmax<<self.fb;self.nan=self.inf|(1<<(self.fb-1))
        self.mask=(1<<self.width)-1
    def sign(self,a):return bool(a&self.signbit)
    def exp(self,a):return (a>>self.fb)&self.expmax
    def is_nan(self,a):return self.exp(a)==self.expmax and bool(a&self.fracmask)
    def is_snan(self,a):return self.is_nan(a) and not (a&(1<<(self.fb-1)))
    def is_inf(self,a):return a&~self.signbit==self.inf
    def is_zero(self,a):return not (a&~self.signbit)
    def value(self,a):
        e=self.exp(a);m=a&self.fracmask
        if e:m|=1<<self.fb
        p=(e-self.bias if e else self.emin)-self.fb
        value=Fraction(m<<p,1) if p>=0 else Fraction(m,1<<-p)
        return -value if self.sign(a) else value
    def pack(self,value,rm,negative_zero=False):
        if not value:return (self.signbit if negative_zero else 0),0
        neg=value<0;v=abs(value);e=log2floor(v)
        step=max(e,self.emin)-self.fb
        n,d=ratio(v,step);q,inexact=round_int(n,d,neg,rm)
        if q>=1<<(self.fb+1):q>>=1;e+=1
        if e>self.emax:
            infinity=rm in (RNE,RMM) or (rm==RUP and not neg) or (rm==RDN and neg)
            return (self.signbit if neg else 0)|(self.inf if infinity else self.inf-1),OF|NX
        flags=NX if inexact else 0
        if e<self.emin:
            # IEEE tininess-after-rounding uses the rounded significand with
            # an UNBOUNDED exponent range. Directed rounding can finally
            # produce the smallest normal while still raising underflow.
            unbounded_e=log2floor(v)
            un,ud=ratio(v,unbounded_e-self.fb)
            uq,_=round_int(un,ud,neg,rm)
            if uq>=1<<(self.fb+1):unbounded_e+=1
            if inexact and unbounded_e<self.emin:flags|=UF
            if q<1<<self.fb:
                return (self.signbit if neg else 0)|q,flags
            e=self.emin
        return (self.signbit if neg else 0)|((e+self.bias)<<self.fb)|(q&self.fracmask),flags
    def zero_sign(self,xzero,xsign,yzero,ysign,rm):
        return xsign if xzero and yzero and xsign==ysign else rm==RDN
    def add(self,a,b,rm,subtract=False):
        sa=self.sign(a);sb=self.sign(b)^subtract
        if self.is_nan(a) or self.is_nan(b):return self.nan,NV if self.is_snan(a) or self.is_snan(b) else 0
        if self.is_inf(a) and self.is_inf(b) and sa!=sb:return self.nan,NV
        if self.is_inf(a):return (self.signbit if sa else 0)|self.inf,0
        if self.is_inf(b):return (self.signbit if sb else 0)|self.inf,0
        value=self.value(a)+(-self.value(b) if subtract else self.value(b))
        return self.pack(value,rm,self.zero_sign(self.is_zero(a),sa,self.is_zero(b),sb,rm))
    def multiply(self,a,b,rm):
        sign=self.sign(a)^self.sign(b);prefix=self.signbit if sign else 0
        if self.is_nan(a) or self.is_nan(b):return self.nan,NV if self.is_snan(a) or self.is_snan(b) else 0
        if (self.is_inf(a) and self.is_zero(b)) or (self.is_zero(a) and self.is_inf(b)):return self.nan,NV
        if self.is_inf(a) or self.is_inf(b):return prefix|self.inf,0
        return self.pack(self.value(a)*self.value(b),rm,sign)
    def divide(self,a,b,rm):
        sign=self.sign(a)^self.sign(b);prefix=self.signbit if sign else 0
        if self.is_nan(a) or self.is_nan(b):return self.nan,NV if self.is_snan(a) or self.is_snan(b) else 0
        if (self.is_zero(a) and self.is_zero(b)) or (self.is_inf(a) and self.is_inf(b)):return self.nan,NV
        if self.is_inf(a):return prefix|self.inf,0
        if self.is_inf(b):return prefix,0
        if self.is_zero(b):return prefix|self.inf,DZ
        return self.pack(self.value(a)/self.value(b),rm,sign)
    def fused(self,a,b,c,rm,negprod=False,negc=False):
        sp=self.sign(a)^self.sign(b)^negprod;sc=self.sign(c)^negc
        bad=(self.is_inf(a) and self.is_zero(b)) or (self.is_zero(a) and self.is_inf(b))
        if any(self.is_nan(x) for x in [a,b,c]):return self.nan,NV if bad or any(self.is_snan(x) for x in [a,b,c]) else 0
        if bad:return self.nan,NV
        if (self.is_inf(a) or self.is_inf(b)) and self.is_inf(c) and sp!=sc:return self.nan,NV
        if self.is_inf(a) or self.is_inf(b):return (self.signbit if sp else 0)|self.inf,0
        if self.is_inf(c):return (self.signbit if sc else 0)|self.inf,0
        p=self.value(a)*self.value(b);z=self.value(c)
        if negprod:p=-p
        if negc:z=-z
        return self.pack(p+z,rm,self.zero_sign(self.is_zero(a) or self.is_zero(b),sp,self.is_zero(c),sc,rm))
    def sqrt(self,a,rm):
        if self.is_nan(a):return self.nan,NV if self.is_snan(a) else 0
        if self.sign(a) and not self.is_zero(a):return self.nan,NV
        if self.is_inf(a) or self.is_zero(a):return a,0
        v=self.value(a);e=log2floor(v)//2;step=max(e,self.emin)-self.fb
        n,d=ratio(v,2*step);q=isqrt(n//d);exact=q*q*d==n
        if not exact:
            left=4*n;right=(2*q+1)**2*d
            inc=[left>right or (left==right and q&1),False,False,True,left>=right][rm]
            q+=int(inc)
        # q * 2**step is the correctly rounded result already; pack exactly.
        rounded=Fraction(q<<step,1) if step>=0 else Fraction(q,1<<-step)
        result,_=self.pack(rounded,RNE)
        return result,(0 if exact else NX|(UF if e<self.emin else 0))
    def compare(self,a,b,op,quiet=False):
        if self.is_nan(a) or self.is_nan(b):
            return 0,NV if self.is_snan(a) or self.is_snan(b) or (op!='eq' and not quiet) else 0
        # Infinity order can use integer sign/magnitude order directly.
        def key(x):return -(x&~self.signbit) if self.sign(x) else x&~self.signbit
        x,y=key(a),key(b)
        return int({'eq':x==y,'lt':x<y,'le':x<=y}[op]),0
    def minmax(self,a,b,maximum=False,propagate_nan=False):
        flags=NV if self.is_snan(a) or self.is_snan(b) else 0
        if (self.is_nan(a) and self.is_nan(b)) or (propagate_nan and (self.is_nan(a) or self.is_nan(b))):return self.nan,flags
        if self.is_nan(a):return b,flags
        if self.is_nan(b):return a,flags
        if self.is_zero(a) and self.is_zero(b):
            sign=(self.sign(a)&self.sign(b)) if maximum else (self.sign(a)|self.sign(b))
            return self.signbit if sign else 0,flags
        less,_=self.compare(a,b,'lt')
        return ((b if less else a) if maximum else (a if less else b)),flags
    def classify(self,a):
        if self.is_nan(a):return 1<<(8 if self.is_snan(a) else 9)
        if self.is_inf(a):return 1<<(0 if self.sign(a) else 7)
        if self.is_zero(a):return 1<<(3 if self.sign(a) else 4)
        return 1<<((2 if self.sign(a) else 5) if self.exp(a)==0 else (1 if self.sign(a) else 6))
    def to_int(self,a,bits,unsigned,rm):
        lo=0 if unsigned else -(1<<(bits-1));hi=(1<<bits)-1 if unsigned else (1<<(bits-1))-1
        if self.is_nan(a):return hi,NV
        if self.is_inf(a):return lo if self.sign(a) else hi,NV
        v=self.value(a);n=abs(v).numerator;d=abs(v).denominator
        q,inexact=round_int(n,d,v<0,rm)
        if v<0:q=-q
        if q<lo:return lo,NV
        if q>hi:return hi,NV
        return q,NX if inexact else 0
    def from_int(self,a,bits,unsigned,rm):
        a&=(1<<bits)-1
        if not unsigned and a>>(bits-1):a-=1<<bits
        return self.pack(Fraction(a),rm)
    def convert(self,a,source,rm):
        if source.is_nan(a):return self.nan,NV if source.is_snan(a) else 0
        if source.is_inf(a):return (self.signbit if source.sign(a) else 0)|self.inf,0
        return self.pack(source.value(a),rm,source.sign(a))

#include <stdio.h>
#include <inttypes.h>
#include "softfloat.h"
int main(void) {
    softfloat_detectTininess=softfloat_tininess_afterRounding;
    softfloat_roundingMode=softfloat_round_max;
    softfloat_exceptionFlags=0;
    float32_t a={UINT32_C(0x00800001)},b={UINT32_C(0x3f7fffff)},c={UINT32_C(0x80000001)};
    float32_t x=f32_mulAdd(a,b,c);
    printf("F32 directed boundary result=%08" PRIx32 " flags=%u\n",x.v,(unsigned)softfloat_exceptionFlags);
    if(x.v!=UINT32_C(0x00800000) || softfloat_exceptionFlags!=3)return 1;
    softfloat_exceptionFlags=0;
    float64_t d={UINT64_C(0x0010000000000001)},e={UINT64_C(0x3fefffffffffffff)},f={UINT64_C(0x8000000000000001)};
    float64_t y=f64_mulAdd(d,e,f);
    printf("F64 directed boundary result=%016" PRIx64 " flags=%u\n",y.v,(unsigned)softfloat_exceptionFlags);
    if(y.v!=UINT64_C(0x0010000000000000) || softfloat_exceptionFlags!=3)return 1;
    softfloat_roundingMode=softfloat_round_near_even;
    softfloat_exceptionFlags=0;
    a.v=UINT32_C(0x00800001);x=f32_mul(a,b);
    if(x.v!=UINT32_C(0x00800000) || softfloat_exceptionFlags!=1)return 1;
    softfloat_exceptionFlags=0;
    d.v=UINT64_C(0x0010000000000001);y=f64_mul(d,e);
    if(y.v!=UINT64_C(0x0010000000000000) || softfloat_exceptionFlags!=1)return 1;
    puts("PASS official SoftFloat F32/F64 tininess-after-rounding boundaries");
    return 0;
}

/* Exact-rational generated FCVT.W/WU.S expectations, default RV32 SoC.
 * Exercise actual instructions, FCSR flags and dynamic FRM, not C casts.
 * All host writes use stock legacy HostIF, NOT HTIF tohost=0x80020000.
 */
#include "vectors.h"
_Static_assert(sizeof(unsigned)==4,"This ELF test targets RV32 integer words");

static void event(unsigned value) {
  *(volatile unsigned *)0x1000000c = value;
}

#define CONVERT(OP, MODE) \
  __asm__ volatile("csrw fflags,zero\n\t" \
                   "fmv.w.x ft0,%2\n\t" \
                   OP " %0,ft0," MODE "\n\t" \
                   "csrr %1,fflags" \
                   : "=r"(value), "=r"(flags) : "r"(bits) : "ft0", "memory")

static unsigned convert(unsigned bits, unsigned kind, unsigned rm, unsigned *out_flags) {
  unsigned value,flags;
  if (kind) {
    switch (rm) {
      case 0: CONVERT("fcvt.wu.s","rne"); break;
      case 1: CONVERT("fcvt.wu.s","rtz"); break;
      case 2: CONVERT("fcvt.wu.s","rdn"); break;
      case 3: CONVERT("fcvt.wu.s","rup"); break;
      case 4: CONVERT("fcvt.wu.s","rmm"); break;
      default: CONVERT("fcvt.wu.s","dyn"); break;
    }
  } else {
    switch (rm) {
      case 0: CONVERT("fcvt.w.s","rne"); break;
      case 1: CONVERT("fcvt.w.s","rtz"); break;
      case 2: CONVERT("fcvt.w.s","rdn"); break;
      case 3: CONVERT("fcvt.w.s","rup"); break;
      case 4: CONVERT("fcvt.w.s","rmm"); break;
      default: CONVERT("fcvt.w.s","dyn"); break;
    }
  }
  *out_flags=flags;
  return value;
}

int main(void) {
  unsigned checked=0;
  for (unsigned i=0;i<CONVERSION_VECTOR_COUNT;i++) {
    const struct conversion_vector *v=&conversion_vectors[i];
    for (unsigned kind=0;kind<2;kind++) {
      for (unsigned selector=0;selector<6;selector++) {
        unsigned mode=(selector==5)?i%5:selector;
        unsigned flags,value,expected=v->data[kind][mode];
#ifdef FP_CONVERSION_WRONG_EXPECTED
        if (i==0 && kind==0 && selector==0) expected^=1;
#endif
        if (selector==5)
          __asm__ volatile("csrw frm,%0" : : "r"(mode) : "memory");
        value=convert(v->bits,kind,selector,&flags);
        if (value!=expected || flags!=v->flags[kind][mode]) {
          event(0xdeadfc32u);
          event(v->bits); event(kind); event(mode);
          event(value); event(expected);
          event(flags); event(v->flags[kind][mode]);
          return 1;
        }
        checked++;
      }
    }
  }
  event(0x46504356u);
  event(checked);
  return checked==CONVERSION_VECTOR_COUNT*12u?0:1;
}

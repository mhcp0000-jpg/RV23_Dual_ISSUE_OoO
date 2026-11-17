.section .text.init,"ax"
.option norvc
.option norelax
.globl _start

.equ original_low, 0x91abcdef89abcdef
.equ original_high, 0x9234567890abcdef
.equ replacement, 0x12345678fedcba98

# v3 is deliberately unaligned for LMUL=8. Scalar moves address one
# register regardless of LMUL. Compare both words of that register.
.macro scalar_case sew, lmul, length, start, fp
  la a0,original
  vl1re64.v v3,(a0)
  vsetivli zero,\length,e\sew,\lmul,tu,mu
  csrwi vstart,\start
  .if \fp
    vfmv.f.s fa0,v3
    fmv.x.d a0,fa0
    .if \sew == 32
      li a1,0xffffffff89abcdef
    .else
      li a1,original_low
    .endif
  .else
    vmv.x.s a0,v3
    .if \sew == 8
      li a1,-17
    .elseif \sew == 16
      li a1,-12817
    .elseif \sew == 32
      li a1,0xffffffff89abcdef
    .else
      li a1,original_low
    .endif
  .endif
  bne a0,a1,fail
  csrr a0,vstart
  bnez a0,fail

  li a3,replacement
  # replacement is intentionally malformed as a single-precision NaN box.
  .if \fp
    fmv.d.x fa1,a3
  .endif
  csrwi vstart,\start
  .if \fp
    vfmv.s.f v3,fa1
  .else
    vmv.s.x v3,a3
  .endif
  csrr a0,vstart
  bnez a0,fail
  la a0,observed
  vs1r.v v3,(a0)
  ld a1,0(a0)
  ld a2,8(a0)
  .if \start != 0 || \length == 0
    li a3,original_low
  .elseif \fp && \sew == 32
    li a3,0x91abcdef7fc00000
  .elseif \sew == 8
    li a3,0x91abcdef89abcd98
  .elseif \sew == 16
    li a3,0x91abcdef89abba98
  .elseif \sew == 32
    li a3,0x91abcdeffedcba98
  .else
    li a3,replacement
  .endif
  bne a1,a3,fail
  li a3,original_high
  bne a2,a3,fail
.endm

.macro scalar_boundaries sew, lmul, fp
  scalar_case \sew, \lmul, 0, 0, \fp
  scalar_case \sew, \lmul, 1, 1, \fp
  scalar_case \sew, \lmul, 0, 1, \fp
  scalar_case \sew, \lmul, 2, 1, \fp
  scalar_case \sew, \lmul, 2, 0, \fp
.endm

.macro illegal_move word
  li s0,\word
  csrwi vstart,1
  .word \word
  bnez s0,fail
  csrr t0,vstart
  li t1,1
  bne t0,t1,fail
.endm

_start:
  la t0,trap
  csrw mtvec,t0
  li t0,0x6600
  csrs mstatus,t0
  csrw fcsr,zero
  li s0,0
  .irp lmul,m1,m8
    .irp sew,8,16,32,64
      scalar_boundaries \sew, \lmul, 0
    .endr
    .irp sew,32,64
      scalar_boundaries \sew, \lmul, 1
    .endr
  .endr

  vsetivli zero,2,e32,m8,tu,mu
  illegal_move 0x40302557   # masked vmv.x.s
  illegal_move 0x4006e1d7   # masked vmv.s.x
  illegal_move 0x40301557   # masked vfmv.f.s
  illegal_move 0x4005d1d7   # masked vfmv.s.f
  vsetivli zero,2,e16,m8,tu,mu
  illegal_move 0x42301557   # half-precision vfmv.f.s requires Zvfh
  illegal_move 0x4205d1d7   # half-precision vfmv.s.f requires Zvfh
  csrr t0,fflags
  bnez t0,fail
  li t1,1
  j finish
trap:
  beqz s0,fail
  csrr t0,mcause
  li t1,2
  bne t0,t1,fail
  csrr t0,mtval
  bne t0,s0,fail
  csrr t0,mepc
  lwu t1,0(t0)
  bne t1,s0,fail
  addi t0,t0,4
  csrw mepc,t0
  li s0,0
  mret
fail:
  li t1,3
finish:
  la t0,tohost
  sd t1,0(t0)
halt:
  j halt

.section .tohost,"aw"
.balign 8
.globl tohost,fromhost
tohost: .dword 0
fromhost: .dword 0

.section .data
.balign 16
original: .dword original_low,original_high
observed: .dword 0,0

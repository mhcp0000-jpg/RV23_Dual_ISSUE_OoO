.section .text.init,"ax"
.option norvc
.option norelax
.globl _start
_start:
  la t0,fail
  csrw mtvec,t0
  li t0,0x6000
  csrs mstatus,t0
  la s1,target
  li s2,0x76543210
  li s6,0x30000000
  li a0,100
  li a1,7
  li a2,14
  li t0,0x3ff0000000000000
  fmv.d.x ft0,t0
  li t0,0x4008000000000000
  fmv.d.x ft1,t0
  fmv.d.x ft2,zero
  li t0,0x7ff0000000000001
  fmv.d.x ft3,t0
  li t0,0x7ff0000000000000
  fmv.d.x ft4,t0
  li t0,0x7ff8000000001234
  fmv.d.x ft5,t0

.macro recovery_case number, instruction:vararg
  li t0,0x401d000000000000
  fmv.d.x fs0,t0
  .if \number == 7
    csrwi fflags,5
    csrw mstatus,zero
  .else
    csrw fflags,zero
    li t0,0x4000
    csrw mstatus,t0
  .endif
  .balign 64
  divu a3,a0,a1
  beq a3,a2,safe\number
  .globl wrong\number,wrong_begin\number,wrong_end\number
wrong_begin\number:
  .if \number == 6
    .rept 8
      fadd.d fs0,fs0,ft0
    .endr
  .endif
wrong\number:
  \instruction
  sd s2,0(s1)
  j fail
wrong_end\number:
safe\number:
  .if \number == 7
    li t0,0x2000
    csrw mstatus,t0
  .endif
  csrr t0,fflags
  .if \number == 7
    li t1,5
    bne t0,t1,fail
  .else
    bnez t0,fail
  .endif
  fmv.x.d t0,fs0
  li t1,0x401d000000000000
  bne t0,t1,fail
  li t1,0x76543210
  bne s2,t1,fail
  ld t0,0(s1)
  li t1,0x123456789abcdef0
  bne t0,t1,fail
  # A correct-path FP request must work after every recovery, including kill.
  fadd.d ft7,ft0,ft1
  fmv.x.d t0,ft7
  li t1,0x4010000000000000
  bne t0,t1,fail
  .if \number == 6
    # Reuse the slow datapath after killing the wrong-path FDIV owner.
    fdiv.d ft7,ft1,ft0
    fmv.x.d t0,ft7
    li t1,0x4008000000000000
    bne t0,t1,fail
  .endif
  csrr t0,fflags
  .if \number == 7
    li t1,5
    bne t0,t1,fail
  .else
    bnez t0,fail
  .endif
.endm

  recovery_case 0, fadd.d fs0,ft0,ft1
  recovery_case 1, feq.d s2,ft3,ft0
  recovery_case 2, fmadd.d fs0,ft4,ft2,ft5
  recovery_case 3, fdiv.d fs0,ft0,ft2
  recovery_case 4, fsd ft1,0(s1)
  recovery_case 5, fld fs0,0(s6)
  recovery_case 6, fdiv.d fs0,fs0,ft1
  recovery_case 7, fadd.d fs0,ft0,ft1
  li t1,1
  j finish
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
tohost:.dword 0
fromhost:.dword 0
.section .data,"aw"
.balign 64
target:.dword 0x123456789abcdef0

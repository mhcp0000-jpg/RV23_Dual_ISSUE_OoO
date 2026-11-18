.section .text.init,"ax"
.option norvc
.option norelax
.globl _start
_start:
  la t0,fail
  csrw mtvec,t0
  li t0,0x6600
  csrs mstatus,t0
  la s0,original
  la s1,target
  li s2,0x76543210
  li s6,0x30000000
  li a0,100
  li a1,7
  li a2,14
  li t0,0x4014000000000000
  fmv.d.x fa0,t0

.macro recovery_case number, instruction:vararg
  vsetivli zero,2,e64,m1,tu,mu
  vle64.v v8,(s0)
  .balign 64
  divu a3,a0,a1
  beq a3,a2,safe\number
  .globl wrong\number,wrong_end\number
wrong\number:
  \instruction
  sd s2,0(s1)
  j fail
wrong_end\number:
safe\number:
  csrr t0,vl
  li t1,2
  bne t0,t1,fail
  csrr t0,vstart
  bnez t0,fail
  li t1,0x76543210
  bne s2,t1,fail
  ld t0,0(s1)
  li t1,0x123456789abcdef0
  bne t0,t1,fail
  la t0,observed
  vs1r.v v8,(t0)
  ld t1,0(t0)
  ld t2,0(s0)
  bne t1,t2,fail
  ld t1,8(t0)
  ld t2,8(s0)
  bne t1,t2,fail
.endm

  recovery_case 0, vse64.v v8,(s1)
  recovery_case 1, vmv.v.i v8,7
  recovery_case 2, vsetivli zero,1,e8,m1,ta,ma
  recovery_case 3, vfmv.s.f v8,fa0
  recovery_case 4, vle64.v v8,(s6)
  recovery_case 5, vmv.x.s s2,v8
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
tohost: .dword 0
fromhost: .dword 0
.section .data,"aw"
.balign 64
original: .dword 0x91abcdef01234567,0x823456789abcdef0
target: .dword 0x123456789abcdef0
.section .bss
.balign 16
observed: .space 16

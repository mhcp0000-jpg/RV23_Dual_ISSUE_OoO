.section .text.init,"ax"
.option norvc
.option norelax
.globl _start

.macro probe phase, width, expected
  li s0,\phase
  sd zero,8(s1)
  lr.\width t0,(s1)
  bnez t0,fail
  wrs.nto
  sc.\width t0,s2,(s1)
  li t1,1
  bne t0,t1,fail
  ld t0,0(s1)
  bnez t0,fail
  ld t0,8(s1)
  li t1,\expected
  bne t0,t1,fail
  ld t0,64(s1)
  li t1,(0xf000000000000000 | \phase)
  bne t0,t1,fail
.endm

.macro interference phase, width, status, expected
  li s0,\phase
  sd zero,0(s1)
  lr.\width t0,(s1)
  bnez t0,fail
1:
  ld t0,0(s3)
  bne t0,s0,1b
  sc.\width t0,s4,(s1)
  li t1,\status
  bne t0,t1,fail
  sc.\width t0,s2,(s1)
  li t1,1
  bne t0,t1,fail
  ld t0,0(s1)
  li t1,\expected
  bne t0,t1,fail
.endm

_start:
  la t0,fail
  csrw mtvec,t0
  csrw mie,zero
  li s1,0x80070000
  li s2,-1
  addi s3,s1,128
  li s4,0x12345678
  sd zero,0(s1)
  sd zero,0(s3)
  probe 1, w, 0x13579abc
  probe 2, d, 0x13579abc
  probe 3, w, 0x1234567813579abc
  probe 4, d, 0x1234567813579abc
  interference 5, w, 0, 0x12345678
  interference 6, d, 0, 0x12345678
  interference 7, w, 1, 0x2468ace0
  interference 8, d, 1, 0x2468ace000000000
  lui t0,0x10000
  li t1,0x57525344
  sw t1,0xc(t0)
  sw zero,0x14(t0)
halt: j halt
fail:
  lui t0,0x10000
  sw s0,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j halt


.section .text.init,"ax"
.option norvc
.option norelax
.globl _start
_start:
  la t0,handler
  csrw mtvec,t0
  li t0,0x0c000004
  li t1,1
  sw t1,0(t0)
  li t0,0x0c002000
  li t1,2
  sw t1,0(t0)
  li t0,0x0c200000
  sw zero,0(t0)
  li s0,0x800a0000
  li s1,0x800a0100
  li s4,0x1234
  sd zero,0(s1)
  li s2,0
  li t0,0x600
  csrs mstatus,t0
  li t0,128
  vsetvli t1,t0,e8,m8,tu,mu
  bne t1,t0,fail
  vmv.v.i v8,5
  li t0,0x800
  csrw mie,t0
  csrsi mstatus,8
  vse8.v v8,(s0)
after_vector:
  sd s4,0(s1)
wait_interrupt:
  beqz s2,wait_interrupt
  csrci mstatus,8
  li t0,1
  bne s2,t0,fail
  ld t0,0(s1)
  bne t0,s4,fail
  li t1,1
  j finish

handler:
  csrr t0,mcause
  li t1,0x800000000000000b
  bne t0,t1,fail
  csrr t0,mepc
  la t1,after_vector
  bltu t0,t1,fail
  la t1,wait_interrupt
  bltu t1,t0,fail
  csrr t0,mtval
  bnez t0,fail
  csrr t0,vstart
  bnez t0,fail
  li t0,0x0c200004
  lw t1,0(t0)
  li t2,1
  bne t1,t2,fail
  sw t1,0(t0)
  mv t0,s0
  li t1,0x0505050505050505
  addi t2,s0,128
verify_bytes:
  ld t3,0(t0)
  bne t3,t1,fail
  addi t0,t0,8
  bne t0,t2,verify_bytes
  addi s2,s2,1
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

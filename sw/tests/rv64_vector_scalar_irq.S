.section .text.init,"ax"
.option norvc
.option norelax
.globl _start
_start:
  la t0,handler
  csrw mtvec,t0
  li t0,0x600
  csrs mstatus,t0
  li s2,14
  li s4,0
  li t0,100
  li t1,7
  vsetivli zero,2,e64,m1,tu,mu
  vmv.v.x v16,t0
  vmv.v.x v24,t1
  li t0,0x0c000004
  li t1,1
  sw t1,0(t0)
  li t0,0x0c002000
  li t1,2
  sw t1,0(t0)
  li t0,0x0c200000
  sw zero,0(t0)
  fence rw,rw
  li t0,0x800
  csrw mie,t0
  csrsi mstatus,8
.globl irq_vector
irq_vector:
  vdivu.vv v8,v16,v24
  addi a4,zero,77
  addi a5,a4,1
wait_irq:
  beqz s4,wait_irq
  csrci mstatus,8
  li t0,1
  bne s4,t0,fail
  li t0,77
  bne a4,t0,fail
  li t0,78
  bne a5,t0,fail
  li t1,1
  j finish
handler:
  csrr t0,mcause
  li t1,0x800000000000000b
  bne t0,t1,fail
  csrr t0,vstart
  bnez t0,fail
  vmv.x.s t0,v8
  bne t0,s2,fail
  li t0,0x0c200004
  lw t1,0(t0)
  li t2,1
  bne t1,t2,fail
  sw t1,0(t0)
  addi s4,s4,1
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

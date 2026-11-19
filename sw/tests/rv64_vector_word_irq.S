.section .text.init,"ax"
.option norvc
.option norelax
.globl _start
_start:
  la t0,handler
  csrw mtvec,t0
  li t0,0x600
  csrs mstatus,t0
  li s0,0x800a0000
  li s1,0x800a0100
  sd zero,0(s1)
  mv t0,s0
  li t1,0x0706050403020100
  li t2,0x0808080808080808
  li t3,16
fill:
  sd t1,0(t0)
  add t1,t1,t2
  addi t0,t0,8
  addi t3,t3,-1
  bnez t3,fill
  ld t0,0(s0)
  ld t0,64(s0)
#if TEST_COLD
  cbo.flush 0(s0)
  addi t0,s0,64
  cbo.flush 0(t0)
#endif
  fence rw,rw
  li s2,128/(DATA_EEW/8)
#if DATA_EEW == 8
  vsetvli t0,s2,e8,m8,tu,mu
#elif DATA_EEW == 16
  vsetvli t0,s2,e16,m8,tu,mu
#else
  vsetvli t0,s2,e32,m8,tu,mu
#endif
  bne t0,s2,fail
  vmv.v.i v8,-1
  li s3,77
  li s4,0
  li t0,0x0c000004
  li t1,1
  sw t1,0(t0)
  li t0,0x0c002000
  li t1,2
  sw t1,0(t0)
  li t0,0x0c200000
  sw zero,0(t0)
  fence iorw,iorw
  li t0,0x800
  csrw mie,t0
  csrsi mstatus,8
.globl irq_vector
irq_vector:
#if DATA_EEW == 8
  vle8.v v8,(s0)
#elif DATA_EEW == 16
  vle16.v v8,(s0)
#else
  vle32.v v8,(s0)
#endif
.globl following_store
following_store:
  sd s3,0(s1)
wait_irq:
  beqz s4,wait_irq
  csrci mstatus,8
  li t0,1
  bne s4,t0,fail
  ld t0,0(s1)
  bne t0,s3,fail
  li t1,1
  j finish
handler:
  csrr t0,mcause
  li t1,0x800000000000000b
  bne t0,t1,fail
  csrr t0,vstart
  bnez t0,fail
  li a0,0
  mv a1,s0
check_all_elements:
  vslidedown.vx v24,v8,a0
  vmv.x.s t0,v24
#if DATA_EEW == 8
  lbu t1,0(a1)
#elif DATA_EEW == 16
  lhu t1,0(a1)
#else
  lwu t1,0(a1)
#endif
  bne t0,t1,fail
  addi a0,a0,1
  addi a1,a1,DATA_EEW/8
  bltu a0,s2,check_all_elements
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

.section .text.init,"ax"
.option norvc
.globl _start
_start:
  lui t0,0x02000
  sw zero,0(t0)
  la t0,m_trap
  csrw mtvec,t0
  li t0,-1
  csrw pmpaddr0,t0
  li t0,15
  csrw pmpcfg0,t0
  li s0,0x80070100
  li s6,0
  addi t0,s0,-8
  li t1,10
  li t2,1
fill:
  sd t2,0(t0)
  addi t2,t2,1
  addi t0,t0,8
  addi t1,t1,-1
  bnez t1,fill
  ld t1,0(s0)                  # populate D-cache line before management
  li t2,2
  bne t1,t2,fail
  addi s1,s0,63
  cbo.clean (s1)
  cbo.flush (s1)
  ld t1,0(s0)                  # must refill the invalidated line
  bne t1,t2,fail
  cbo.inval (s1)
  ld t1,0(s0)
  bne t1,t2,fail
  lr.d t1,(s0)
  cbo.zero (s1)                # full aligned 64-byte block, not 64 bytes at rs1
  sc.d t1,zero,(s0)
  li t2,1
  bne t1,t2,fail
  li t0,8
  mv t1,s0
check_zero:
  ld t2,0(t1)
  bnez t2,fail
  addi t1,t1,8
  addi t0,t0,-1
  bnez t0,check_zero
  ld t1,-8(s0)
  li t2,1
  bne t1,t2,fail
  ld t1,64(s0)
  li t2,10
  bne t1,t2,fail
  csrw menvcfg,zero
  csrw senvcfg,zero
  la t0,u_entry
  csrw mepc,t0
  csrw mstatus,zero
  mret
u_entry:
  li a4,2
  la t0,u_clean
  lwu a5,0(t0)
u_clean:
  cbo.clean (s0)               # menvcfg and senvcfg independently gate U
  li t0,2
  bne s6,t0,fail
  cbo.inval (s0)
  cbo.flush (s0)
  li t0,0x11223344
  sd t0,0(s0)
  li s1,0xfe0000008007013f
  cbo.zero (s1)                # Ssnpm also applies to cache-block operations
  ld t0,0(s0)
  bnez t0,fail
  li s1,0x02000003
  li a4,7
  mv a5,s1
  cbo.zero (s1)                # no peripheral writes
  cbo.clean (s1)               # uncached management performs no MMIO load
  li s1,-1
  prefetch.r 0(s1)             # faulting hints never trap or access memory
  prefetch.w 0(s1)
  prefetch.i 0(s1)
  li t0,3
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x43424f31
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:j 1b
m_trap:
  csrr t4,mcause
  bne t4,a4,fail
  csrr t4,mtval
  bne t4,a5,fail
  addi s6,s6,1
  li t4,1
  beq s6,t4,enable_machine
  li t4,2
  beq s6,t4,enable_supervisor
  csrr t4,mepc
  addi t4,t4,4
  csrw mepc,t4
  mret
enable_machine:
  li t4,0xf0
  csrw menvcfg,t4
  mret
enable_supervisor:
  li t4,0x2000000f0
  csrw senvcfg,t4
  mret
fail:
  lui t0,0x10000
  li t1,1
  sw t1,0x14(t0)
  j 1b

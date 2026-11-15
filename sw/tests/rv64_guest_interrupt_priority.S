.section .text.init,"ax"
.option norvc
.option norelax
.globl _start
_start:
  lui t0,0x02000
  sw zero,0(t0)
  la t0,fail
  csrw mtvec,t0
  li t0,-1
  csrw pmpaddr0,t0
  li t0,31
  csrw pmpcfg0,t0
  li t0,0x2222          # SEI, SSI, STI and LCOFI
  csrw mideleg,t0
  csrw mip,t0
  li t0,1<<10
  csrw medeleg,t0       # VS ECALL returns control to HS.
  la t0,hs_trap
  csrw stvec,t0
  la t0,hs_entry
  csrw mepc,t0
  li t0,0x800
  csrw mstatus,t0
  mret

hs_entry:
  li s0,0
  la s1,hs_priorities
  li t0,0x2222
  csrw sie,t0
  li t0,0x444
  csrw hie,t0
  csrw hvip,t0
  csrsi sstatus,2
hs_resume:
  li t0,7
  bne s0,t0,fail

  # The same pending virtual interrupt sources are now VS-delegated.
  # Re-enable SSI while still in HS with SIE clear, then enter VS.
  csrci sstatus,2
  csrwi sie,2
  li t0,0x444
  csrw hideleg,t0
  li t0,0x222
  csrw vsie,t0
  csrwi vsstatus,2
  la t0,vs_trap
  csrw vstvec,t0
  li t0,0x180
  csrw hstatus,t0
  la t0,vs_resume
  csrw sepc,t0
  li t0,0x100
  csrw sstatus,t0
  la s2,vs_priorities
  li s3,0
  sret

vs_resume:
  li t0,3
  bne s3,t0,fail
  ecall
  j fail

hs_trap:
  csrr a4,scause
  bgez a4,hs_exception
  slli t0,a4,1
  srli t0,t0,1
  lbu t1,0(s1)
  bne t0,t1,fail
  csrr t1,sepc
  li t2,7
  bgeu s0,t2,hs_preempt
  la t2,hs_resume
  bne t1,t2,fail
  j hs_disable_source
hs_preempt:
  la t2,vs_resume
  bne t1,t2,fail
  csrr t1,hstatus
  andi t1,t1,0x180
  li t2,0x180
  bne t1,t2,fail
hs_disable_source:
  li t1,1
  sll t1,t1,t0
  andi t2,t1,0x444
  bnez t2,hs_disable_virtual
  csrc sie,t1
  j hs_next
hs_disable_virtual:
  csrc hie,t1
hs_next:
  addi s0,s0,1
  addi s1,s1,1
  sret

vs_trap:
  csrr a5,scause
  bgez a5,fail
  slli t0,a5,1
  srli t0,t0,1
  lbu t1,0(s2)
  bne t0,t1,fail
  csrr t1,sepc
  la t2,vs_resume
  bne t1,t2,fail
  li t1,1
  sll t1,t1,t0
  csrc sie,t1
  addi s2,s2,1
  addi s3,s3,1
  sret

hs_exception:
  li t0,10
  bne a4,t0,fail
  li t0,8
  bne s0,t0,fail
  li t0,3
  bne s3,t0,fail
  lui t0,0x10000
  li t1,0x49525150
  sw t1,0xc(t0)
  sw zero,0x14(t0)
halt:
  j halt
fail:
  lui t0,0x10000
  sw s0,0xc(t0)
  sw s3,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j halt

.balign 4
hs_priorities:
  .byte 9,1,5,10,2,6,13,1
vs_priorities:
  .byte 9,1,5

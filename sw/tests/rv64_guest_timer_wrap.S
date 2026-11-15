.section .text.init,"ax"
.option norvc
.option norelax
.globl _start

.macro pending expected
  csrr a5,hip
  andi t1,a5,0x40
  li t2,\expected
  bne t1,t2,fail
.endm

_start:
  lui t0,0x02000
  sw zero,0(t0)
  la t0,fail
  csrw mtvec,t0
  li t0,-1
  csrw pmpaddr0,t0
  li t0,31
  csrw pmpcfg0,t0
  li t0,2
  csrw mcounteren,t0
  csrw hcounteren,t0
  li t0,0x8000000000000000
  csrw menvcfg,t0
  csrw henvcfg,t0
  li t0,1<<10
  csrw medeleg,t0
  la t0,hs_trap
  csrw stvec,t0
  la t0,hs_entry
  csrw mepc,t0
  li t0,0x800
  csrw mstatus,t0
  mret

hs_entry:
  li s0,0x0200bff8
  li t0,-0x110000
  csrw htimedelta,t0
  li t0,0x20000
  csrw vstimecmp,t0
  li t0,0x100000
  sd t0,0(s0)
  csrw hvip,zero
  pending 0x40              # Guest time is near UINT64_MAX.
  li t0,0x120000
  sd t0,0(s0)
  pending 0                 # Guest time wrapped to about 0x10000.
  li t0,0x40
  csrw hvip,t0
  pending 0x40              # Injection alone sets VSTIP.
  csrw hvip,zero
  pending 0
  li t0,0x10000
  csrw vstimecmp,t0
  pending 0x40              # Unsigned post-wrap comparison is now true.
  li t0,0x40
  csrw hvip,t0
  pending 0x40
  csrw hvip,zero
  pending 0x40              # Clearing injection leaves the timer pending.
  li t0,0x20000
  csrw vstimecmp,t0
  pending 0
  li t0,0x40
  csrw hideleg,t0
  csrw hvip,t0
  li t0,0x20
  csrw vsie,t0
  csrw vsstatus,zero        # Enter VS with interrupts disabled.
  la t0,vs_handler
  csrw vstvec,t0
  la t0,vs_entry
  csrw sepc,t0
  li t0,0x180
  csrw hstatus,t0
  li t0,0x100
  csrw sstatus,t0
  sret

vs_entry:
  csrr a0,time
  li t0,0x10000
  bltu a0,t0,fail
  li t0,0x20000
  bgeu a0,t0,fail
  csrr a1,sip
  li t0,0x20
  bne a1,t0,fail
  csrsi sstatus,2
vs_interrupt_pc:
  j fail
vs_handler:
  csrr a2,scause
  li t0,0x8000000000000005
  bne a2,t0,fail
  csrr t0,sepc
  la t1,vs_interrupt_pc
  bne t0,t1,fail
  ecall
  j fail
hs_trap:
  csrr t0,scause
  li t1,10
  bne t0,t1,fail
  pending 0x40
  csrw hvip,zero
  pending 0
  lui t0,0x10000
  li t1,0x54494d57
  sw t1,0xc(t0)
  sw zero,0x14(t0)
halt:
  j halt
fail:
  lui t0,0x10000
  li t1,1
  sw t1,0x14(t0)
  j halt

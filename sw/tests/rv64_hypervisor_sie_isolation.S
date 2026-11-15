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
  li t0,0x444
  csrw mie,t0
  csrr t1,hie
  bne t0,t1,fail
  csrr t1,vsie
  bnez t1,fail
  csrw hideleg,t0
  csrr t1,vsie
  li t2,0x222
  bne t1,t2,fail
  csrw hideleg,zero
  csrw hie,zero
  csrr t1,mie
  bnez t1,fail
  li t0,2
  csrw mideleg,t0
  li t0,1<<10
  csrw medeleg,t0
  la t0,hs_trap
  csrw stvec,t0
  la t0,hs_entry
  csrw mepc,t0
  li t0,0x800
  csrw mstatus,t0
  li s0,0
  li s1,0
  mret

hs_entry:
  # A write to HS sie may enable SSI but must not enable VSEI.
  li t0,0x446
  csrw sie,t0
  li t0,0x400
  csrw hvip,t0
  csrsi sstatus,2
hs_disabled_next:
  csrr t1,sie
  li t0,2
  bne t1,t0,fail
  csrr t1,hie
  bnez t1,fail
  csrr t1,sip
  bnez t1,fail
  csrr t1,hip
  li t0,0x400
  bne t1,t0,fail

  # HIE is the owner of VSEIE. Injected VSEIP now traps to HS.
  li s0,1
  csrw hie,t0
hs_enabled_next:
  li t0,1
  bne s1,t0,fail

  # Delegate VSEI to VS. The VS trap sees the translated code 9.
  li s0,2
  li t0,0x400
  csrw hideleg,t0
  csrw hvip,t0
  li t0,0x200
  csrw vsie,t0
  li t0,2
  csrw vsstatus,t0
  la t0,vs_trap
  csrw vstvec,t0
  la t0,guest_entry
  csrw sepc,t0
  li t0,0x180
  csrw hstatus,t0
  li t0,0x100
  csrw sstatus,t0
  sret

guest_entry:
  j fail

vs_trap:
  csrr t0,scause
  li t1,0x8000000000000009
  bne t0,t1,fail
  csrr t0,sepc
  la t1,guest_entry
  bne t0,t1,fail
  csrr t0,sip
  li t1,0x200
  bne t0,t1,fail
  ecall
  j fail

hs_trap:
  csrr t0,scause
  li t1,0x800000000000000a
  bne t0,t1,hs_ecall
  csrr t0,sepc
  bnez s0,hs_enabled
  la t1,hs_disabled_next
  bne t0,t1,fail
  li a0,0x42414449             # Pre-fix spurious interrupt marker.
  li a1,1
  j finish
hs_enabled:
  li t1,1
  bne s0,t1,fail
  la t1,hs_enabled_next
  bne t0,t1,fail
  csrw hvip,zero
  csrw hie,zero
  addi s1,s1,1
  sret
hs_ecall:
  li t1,10
  bne t0,t1,fail
  li t0,2
  bne s0,t0,fail
  li t0,1
  bne s1,t0,fail
  li a0,0x48534945
  li a1,0
  j finish
fail:
  li a0,0x4641494c
  li a1,2
finish:
  lui t0,0x10000
  sw a0,0xc(t0)
  sw a1,0x14(t0)
1:j 1b

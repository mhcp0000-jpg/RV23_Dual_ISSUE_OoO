.section .text.init,"ax"
.option norvc
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
  li sp,0x800f8000
  li t0,0x78
  csrw mcountinhibit,t0
  li t0,0x7f
  csrw mcounteren,t0
  csrw hcounteren,t0
  csrw scounteren,t0
  li t0,0x2000
  csrw mideleg,t0
  csrw mie,t0
  li t0,0xf0b7ff
  csrw medeleg,t0
  la t0,hs_trap
  csrw stvec,t0
  # Counter 3: retirements in HS only, with overflow enabled (OF=0).
  li t0,0x5c00000000000002
  csrw mhpmevent3,t0
  li t0,-4
  csrw mhpmcounter3,t0
  # Counter 4: cycles in VS only. It overflows immediately after HS SRET.
  li t0,0x7400000000000001
  csrw mhpmevent4,t0
  li t0,-1
  csrw mhpmcounter4,t0
  li t0,0x60
  csrw mcountinhibit,t0
  la t0,hs_entry
  csrw mepc,t0
  li t0,0x802                # MPP=S, HS SIE=1
  csrw mstatus,t0
  li s6,0
  li s7,1
  mret
hs_entry:
  # Service the HS overflow before preparing sepc for a guest return. An
  # intervening HS interrupt legitimately replaces sepc with its own boundary.
  li t0,1
wait_hs_irq:
  bne s6,t0,wait_hs_irq
  li t0,0x180
  csrw hstatus,t0
  la t0,guest_entry
  csrw sepc,t0
  li t0,0x100                # HS SIE=0; LCOFI must still preempt a guest
  csrw sstatus,t0
  sret
guest_entry:
  li s7,2
  li t0,2
  bne s6,t0,fail
  csrr t0,hpmcounter4
  beqz t0,fail
  csrr t0,scountovf
  li t1,0x18
  bne t0,t1,fail
  li a0,1
  ecall
1:j 1b
hs_trap:
  addi sp,sp,-32
  sd t0,0(sp)
  sd t1,8(sp)
  sd t2,16(sp)
  csrr t0,scause
  li t1,0x800000000000000d
  bne t0,t1,guest_done
  addi s6,s6,1
  li t0,1
  bne s6,t0,virtual_overflow
  csrr t0,hstatus
  andi t0,t0,0x80
  bnez t0,fail
  csrr t0,scountovf
  li t1,8
  bne t0,t1,fail
  j clear_pending
virtual_overflow:
  li t0,2
  bne s6,t0,fail
  csrr t0,hstatus
  andi t0,t0,0x180
  li t1,0x180
  bne t0,t1,fail
  csrr t0,scountovf
  li t1,0x18
  bne t0,t1,fail
clear_pending:
  csrw sip,zero             # clears pending, preserves the counters' OF bits
  ld t0,0(sp)
  ld t1,8(sp)
  ld t2,16(sp)
  addi sp,sp,32
  sret                      # retry the saved boundary; never skip an IRQ PC
guest_done:
  li t1,10
  bne t0,t1,fail
  li t0,2
  bne s6,t0,fail
  li t0,1
  bne a0,t0,fail
  csrr t1,hpmcounter4
  addi t2,t1,1
  addi t2,t2,1
  csrr t0,hpmcounter4
  bne t0,t1,fail            # VSINH filtering stops this counter in HS
  csrr t0,scountovf
  li t1,0x18
  bne t0,t1,fail
  lui t0,0x10000
  li t1,0x48504d31
  sw t1,0xc(t0)
  sw zero,0x14(t0)
  j 1b
fail:
  lui t0,0x10000
  sw s7,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j 1b

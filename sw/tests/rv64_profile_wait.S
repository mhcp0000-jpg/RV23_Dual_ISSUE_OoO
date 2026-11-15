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
  li s0,0x80070000
  sd zero,0(s0)
  li s6,0
  wrs.nto                       # empty reservation resumes immediately
  lr.d t1,(s0)
  csrr s1,cycle
  wrs.sto
  csrr s2,cycle
  sub s2,s2,s1
  li t0,1000
  bltu s2,t0,fail
  li t0,3000
  bgtu s2,t0,fail
  sc.d t1,zero,(s0)             # WRS does not consume the reservation
  bnez t1,fail
  lr.d t1,(s0)
  li t0,8
  csrw mie,t0
  lui t0,0x02000
  li t1,1
  sw t1,0(t0)                   # locally enabled MSIP, global MIE clear
  wrs.nto
  sw zero,0(t0)
  csrw mie,zero
  la t0,s_entry
  csrw mepc,t0
  li t0,0x300800                # TVM=1, TW=1, MPP=S
  csrw mstatus,t0
  mret
s_entry:
  sfence.w.inval                # ordering fences must work with TVM=1
  sfence.inval.ir
  li a4,0x16000073
  sinval.vma zero,zero                    # TVM permission trap
  li t0,1
  bne s6,t0,fail
  sfence.w.inval
  sinval.vma zero,zero
  sfence.inval.ir
  la t0,u_entry
  csrw sepc,t0
  csrw sstatus,zero
  sret
u_entry:
  wrs.nto                       # TW=1 but no valid reservation: no trap
  lr.d t1,(s0)
  wrs.sto                       # STO is legal in U with TW=1
  sc.d t1,zero,(s0)
  bnez t1,fail
  lr.d t1,(s0)
  li a4,0x00d00073
  wrs.nto                       # valid reservation + TW eventually traps
  li t0,2
  bne s6,t0,fail
  wrs.nto                       # trap cleared LR; no second TW trap
  li a4,0x18000073
  sfence.w.inval                # U-mode ordering fence is illegal
  li a4,0x18100073
  sfence.inval.ir
  li a4,0x16000073
  sinval.vma zero,zero
  li t0,5
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x57525331
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:j 1b
m_trap:
  csrr t4,mcause
  li t5,2
  bne t4,t5,fail
  csrr t4,mtval
  bne t4,a4,fail
  addi s6,s6,1
  csrr t4,mstatus
  li t5,0x100000
  not t5,t5
  and t4,t4,t5                  # remove TVM, retain TW for U WRS
  csrw mstatus,t4
  csrr t4,mepc
  addi t4,t4,4
  csrw mepc,t4
  mret
fail:
  lui t0,0x10000
  li t1,1
  sw t1,0x14(t0)
  j 1b

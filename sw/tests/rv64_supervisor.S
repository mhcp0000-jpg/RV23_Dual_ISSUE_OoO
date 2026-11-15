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
  li t0,7
  csrw mcounteren,t0
  li t0,1
  slli t0,t0,63
  csrw menvcfg,t0
  la t0,s_trap
  csrw stvec,t0
  li t0,256
  csrw medeleg,t0
  la t0,s_entry
  csrw mepc,t0
  li t0,0x800
  csrw mstatus,t0
  mret
s_entry:
  csrr t0,sstatus
  srli t0,t0,32
  andi t0,t0,3
  li t1,2
  bne t0,t1,fail
  csrw satp,zero
  sfence.vma zero,zero
  li t0,-1
  csrw stimecmp,t0
  csrr t0,time
  la t0,u_entry
  csrw sepc,t0
  li t0,0x20
  csrw sstatus,t0
  li a0,0
  sret
u_entry:
u_ecall:
  ecall
  li t0,1
  bne a0,t0,fail
u_illegal:
  mret
  j fail
s_trap:
  csrr t0,scause
  li t1,8
  bne t0,t1,fail
  csrr t0,sepc
  la t1,u_ecall
  bne t0,t1,fail
  csrr t2,stval
  bnez t2,fail
  csrr t2,sstatus
  andi t2,t2,256
  bnez t2,fail
  addi t0,t0,4
  csrw sepc,t0
  li a0,1
  sret
m_trap:
  csrr t0,mcause
  li t1,2
  bne t0,t1,fail
  csrr t0,mepc
  la t1,u_illegal
  bne t0,t1,fail
  csrr t0,mtval
  li t1,0x30200073
  bne t0,t1,fail
  csrr t0,mstatus
  srli t0,t0,11
  andi t0,t0,3
  bnez t0,fail
  la t0,s_exit
  csrw mepc,t0
  li t0,0x800
  csrw mstatus,t0
  mret
s_exit:
  csrr t0,sstatus
  lui t0,0x10000
  li t1,0x53555031
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:wfi
  j 1b
fail:
  lui t0,0x10000
  li t1,1
  sw t1,0x14(t0)
  j 1b

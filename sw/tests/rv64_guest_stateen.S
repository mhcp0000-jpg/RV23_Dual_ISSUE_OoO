.section .text.init,"ax"
.option norvc
.option norelax
.globl _start

.macro probe csr, selector, expected=0
  mv s2,zero
  andi s1,s0,\selector
  la s3,1f
1:
  csrr a4,\csr
  bnez s1,2f
  li t0,22
  bne s2,t0,fail
  j 3f
2:
  bnez s2,fail
  li t0,\expected
  bne a4,t0,fail
3:
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
  li t0,(1<<10)|(1<<22)
  csrw medeleg,t0
  la t0,hs_trap
  csrw stvec,t0
  la t0,hs_entry
  csrw mepc,t0
  li t0,0x800
  csrw mstatus,t0
  mret

hs_entry:
  csrwi senvcfg,1
  la s4,masks
  li s0,0
  li s5,7
next_guest:
  lbu s0,0(s4)
  slli t0,s0,63
  srli t1,s0,4
  slli t1,t1,62
  or t0,t0,t1
  csrw hstateen0,t0
  slli t0,s0,62
  li t1,0x8000000000000000
  and t0,t0,t1
  csrw hstateen1,t0
  slli t0,s0,61
  and t0,t0,t1
  csrw hstateen2,t0
  slli t0,s0,60
  and t0,t0,t1
  csrw hstateen3,t0
  li t0,0x180
  csrw hstatus,t0
  la t0,guest_entry
  csrw sepc,t0
  li t0,0x100
  csrw sstatus,t0
  sret

guest_entry:
  probe sstateen0,1
  probe sstateen1,2
  probe sstateen2,4
  probe sstateen3,8
  probe senvcfg,16,1
  probe hstateen0,0
  ecall
  j fail

hs_trap:
  csrr t0,scause
  li t1,10
  beq t0,t1,guest_done
  li t1,22
  bne t0,t1,fail
  bnez s1,fail
  bnez s2,fail
  mv s2,t0
  csrr t0,sepc
  bne t0,s3,fail
  lwu t1,0(t0)
  csrr t2,stval
  bne t1,t2,fail
  csrr t2,htval
  bnez t2,fail
  csrr t2,hstatus
  andi t2,t2,0x1c0
  li t1,0x180
  bne t2,t1,fail
  addi t0,t0,4
  csrw sepc,t0
  sret

guest_done:
  addi s4,s4,1
  addi s5,s5,-1
  bnez s5,next_guest
  lui t0,0x10000
  li t1,0x53544154
  sw t1,0xc(t0)
  sw zero,0x14(t0)
halt:
  j halt
fail:
  lui t0,0x10000
  sw s0,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j halt
.balign 4
masks:
  .byte 0,1,2,4,8,16,31

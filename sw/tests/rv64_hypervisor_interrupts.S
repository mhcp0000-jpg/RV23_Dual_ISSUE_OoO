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
  li t0,7
  csrw mcounteren,t0
  csrw scounteren,t0
  csrw hcounteren,t0
  li t0,0x8000000000000000
  csrw menvcfg,t0
  csrw henvcfg,t0
  li t0,0xf0b7ff
  csrw medeleg,t0
  la t0,hs_trap
  csrw stvec,t0
  li t0,0x444
  csrw hideleg,t0
  li t0,1000000
  csrw htimedelta,t0
  la t0,vs_vectors
  ori t0,t0,1
  csrw vstvec,t0
  li t0,0x22
  csrw vsie,t0
  li t0,2
  csrw vsstatus,t0
  la t0,hs_entry
  csrw mepc,t0
  li t0,0x800
  csrw mstatus,t0
  li s6,0
  li s7,0
  li s8,0
  mret
hs_entry:
  li t0,0x180
  csrw hstatus,t0
  la t0,guest_entry
  csrw sepc,t0
  li t0,0x100
  csrw sstatus,t0
  sret
guest_entry:
  li s7,1
  lui t0,0x0200c
  ld t1,-8(t0)              # physical CLINT mtime
  csrr t2,time
  sub t2,t2,t1
  li t3,1000000
  bltu t2,t3,guest_fail
  li t3,1100000
  bgeu t2,t3,guest_fail
  li a0,0
  ecall                     # request a VS software interrupt
  li t0,1
  bne s8,t0,guest_fail
  li s7,2
  csrr t0,time
  addi t0,t0,1000
  csrw stimecmp,t0          # guest Sstc alias uses offset time
timer_wait:
  li t0,2
  bne s8,t0,timer_wait
  li s7,3
  csrw scounteren,zero      # VU counter access is HS-qualified but denied
  li t0,0x100
  csrc sstatus,t0
  la t0,vu_entry
  csrw sepc,t0
  sret
vu_entry:
  csrr t0,cycle             # cause 22, rather than an illegal instruction
  csrr t0,sstatus           # VS CSR access from VU also cause 22
  li a0,1
  ecall                     # VU ECALL cause 8, exits to HS
guest_fail:
  li a0,255
  ecall
1:j 1b
.balign 256
vs_vectors:
  j guest_fail
  j vs_software             # guest interrupt code 1
  j guest_fail
  j guest_fail
  j guest_fail
  j vs_timer                # guest interrupt code 5
vs_software:
  csrr t0,scause
  li t1,0x8000000000000001
  bne t0,t1,guest_fail
  csrr t0,stval
  bnez t0,guest_fail
  csrw sip,zero
  addi s8,s8,1
  sret
vs_timer:
  csrr t0,scause
  li t1,0x8000000000000005
  bne t0,t1,guest_fail
  csrr t0,stval
  bnez t0,guest_fail
  li t0,-1
  csrw stimecmp,t0
  addi s8,s8,1
  sret
hs_trap:
  addi s6,s6,1
  csrr t0,scause
  li t1,22
  beq t0,t1,vu_virtual
  li t1,8
  beq t0,t1,finish
  li t1,10
  bne t0,t1,fail
  bnez a0,fail
  li t0,4
  csrw hvip,t0
  j resume
vu_virtual:
  li t0,3
  bne s7,t0,fail
  csrr t0,hstatus
  andi t0,t0,0x180
  li t1,0x80                # SPV=1, SPVP=0 for a VU trap
  bne t0,t1,fail
resume:
  csrr t0,sepc
  addi t0,t0,4
  csrw sepc,t0
  sret
finish:
  li t0,1
  bne a0,t0,fail
  li t0,4
  bne s6,t0,fail
  li t0,2
  bne s8,t0,fail
  lui t0,0x10000
  li t1,0x48595033
  sw t1,0xc(t0)
  sw zero,0x14(t0)
  j 1b
fail:
  lui t0,0x10000
  sw s7,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j 1b

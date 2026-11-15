/* Stock TIM/legacy HostIF directed test; not HTIF/server mailbox or DV. */
  .section .text.init,"ax",@progbits
  .option norvc
  .option norelax
  .globl _start
_start:
  la sp,__stack_top
  csrw mie,zero
  csrci mstatus,8
  la t0,unexpected_trap
  csrw mtvec,t0
  li t0,0x6000
  csrs mstatus,t0
  call main
  li t0,0x10000000
  sw a0,20(t0)
1: j 1b

unexpected_trap:
  li t0,0x10000000
  li t1,0xdeadfc32
  sw t1,12(t0)
  csrr t1,mcause
  sw t1,12(t0)
  csrr t1,mepc
  sw t1,12(t0)
  csrr t1,mtval
  sw t1,12(t0)
  li t1,1
  sw t1,20(t0)
2: j 2b

.section .text.init,"ax",@progbits
.option norvc
.globl _start
_start:
  lui t0,0x02000
  sw zero,0(t0)
  la sp,__stack_top
  la t0,__bss_start
  la t1,__bss_end
1:
  bgeu t0,t1,2f
  sb zero,0(t0)
  addi t0,t0,1
  j 1b
2:
  li t0,0x6600
  csrs mstatus,t0
  call main
  lui t0,0x10000
  sw a0,0x14(t0)
3:
  wfi
  j 3b

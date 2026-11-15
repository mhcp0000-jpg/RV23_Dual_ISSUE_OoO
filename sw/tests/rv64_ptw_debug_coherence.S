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
  li t0,0x4000000000000000
  csrw menvcfg,t0
  la t0,root
  li t1,0x40000000000000c7
  sd t1,0(t0)
  li t1,0x200000cf
  sd t1,16(t0)
  la t1,level1
  srli t1,t1,2
  ori t1,t1,1
  sd t1,8(t0)
  la t0,level1
  la t1,level0
  srli t1,t1,2
  ori t1,t1,1
  sd t1,0(t0)
  la t0,level0
  li t1,(0x80030000 >> 2) | 0xc7
  sd t1,0(t0)
  li t0,0x80030000
  li t1,0x123456789abcdef
  sd t1,0(t0)
  li t0,0x80031000
  li t1,0x76543210fedcba98
  sd t1,0(t0)
  li s2,0x80033f00
  sd zero,0(s2)
  la t0,root
  srli t0,t0,12
  li t1,0x8000000000000000
  or t0,t0,t1
  csrw satp,t0
  sfence.vma
  la t0,s_entry
  csrw mepc,t0
  li t0,0x800
  csrw mstatus,t0
  mret
s_entry:
  li s0,0x40000000
  ld t0,0(s0)
  li t1,0x123456789abcdef
  bne t0,t1,fail
  li s1,1
next_update:
  # Force a resident PTE cache line immediately before the external update.
  la t0,level0
  ld t1,0(t0)
  sd zero,0(s2)
  lui t0,0x10000
  li t1,0x50540000
  or t1,t1,s1
  sw t1,0xc(t0)
wait_external:
  ld t0,0(s2)
  bne t0,s1,wait_external
  sfence.vma s0,zero
  ld t0,0(s0)
  andi t1,s1,1
  beqz t1,expect_a
  li t1,0x76543210fedcba98
  j check_value
expect_a:
  li t1,0x123456789abcdef
check_value:
  bne t0,t1,fail
  addi s1,s1,1
  li t0,17
  bne s1,t0,next_update
  lui t0,0x10000
  li t1,0x50545743
  sw t1,0xc(t0)
  sw zero,0x14(t0)
halt:
  j halt
fail:
  lui t0,0x10000
  sw s1,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j halt
.section .bss,"aw",@nobits
.balign 4096
root:.space 4096
level1:.space 4096
level0:.space 4096

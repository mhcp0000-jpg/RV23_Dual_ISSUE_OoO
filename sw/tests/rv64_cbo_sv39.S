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
  li t0,15
  csrw pmpcfg0,t0
  li t0,1
  slli t0,t0,62
  ori t0,t0,0xf0
  csrw menvcfg,t0
  la t1,root
  li t0,0x40000000000000c7
  sd t0,0(t1)
  li t0,0x200000cf
  sd t0,16(t1)
  la t0,level1
  srli t0,t0,2
  ori t0,t0,1
  sd t0,8(t1)
  la t1,level1
  la t0,level0
  srli t0,t0,2
  ori t0,t0,1
  sd t0,0(t1)
  la t1,level0
  li t0,(0x80030000 >> 2) | 0xc7
  sd t0,24(t1)
  li t0,(0x80031000 >> 2) | 0x43
  sd t0,32(t1)
  li t0,(0x80032000 >> 2) | 0x47
  sd t0,40(t1)                  # W=1, A=1, D=0 -> AMO store page fault
  li t0,(0x80034000 >> 2) | 0xd7
  sd t0,64(t1)                  # user RW, SUM initially clear
  li t0,(0x80050000 >> 2) | 0xc7 | (1 << 61)
  sd t0,96(t1)                  # NC SRAM still supports atomics
  li t0,(0x80051000 >> 2) | 0xc7 | (1 << 62)
  sd t0,104(t1)                 # PBMT IO does not support atomics
  li t0,0x80030000
  li t1,10
  sd t1,0(t0)
  li t0,0x80031000
  li t1,0x123456789abcdef0
  sd t1,0(t0)
  li t0,0x80032000
  li t1,20
  sd t1,0(t0)
  li t0,0x80034000
  sd t1,0(t0)
  li t0,0x80050000
  li t1,30
  sd t1,0(t0)
  li t0,0x80051000
  sd t1,0(t0)
  la t0,root
  srli t0,t0,12
  li t1,8
  slli t1,t1,60
  or t0,t0,t1
  csrw satp,t0
  sfence.vma
  la t0,s_trap
  csrw stvec,t0
  li t0,0xb080
  csrw medeleg,t0
  la t0,s_entry
  csrw mepc,t0
  li t0,0x800
  csrw mstatus,t0
  li s6,0
  mret
s_entry:
  li s0,0x40003003
  cbo.clean (s0)
  cbo.flush (s0)
  cbo.inval (s0)
  cbo.zero (s0)
  li s1,0x80030000
  ld t0,0(s1)
  bnez t0,fail
  li s1,0x40004003
  cbo.clean (s1)               # R-only, no D, management must be allowed
  cbo.flush (s1)
  li a4,15
  mv a5,s1
  cbo.zero (s1)
  li s1,0x80031000
  ld t1,0(s1)
  li t2,0x123456789abcdef0
  bne t1,t2,fail
  li s1,0x40005003
  cbo.clean (s1)               # RW with D=0 still permits management
  mv a5,s1
  cbo.zero (s1)                # ZERO must require D and write permission
  li s1,0x80032000
  ld t1,0(s1)
  li t2,20
  bne t1,t2,fail
  li s1,0x40006003
  mv a5,s1
  cbo.clean (s1)               # load-side translation fault reports store cause
  cbo.zero (s1)
  li t0,4
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x43425639
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:wfi
  j 1b
s_trap:
  csrr t4,scause
  bne t4,a4,fail
  csrr t4,stval
  bne t4,a5,fail
  addi s6,s6,1
  csrr t4,sepc
  addi t4,t4,4
  csrw sepc,t4
  sret
fail:
  lui t0,0x10000
  li t1,1
  sw t1,0x14(t0)
  j 1b
.section .bss,"aw",@nobits
.balign 4096
root:.space 4096
level1:.space 4096
level0:.space 4096

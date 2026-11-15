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
  csrw menvcfg,t0
  la t1,root
  li t0,0x40000000000000c7
  sd t0,0(t1)                  # 1 GiB identity MMIO, PBMT=IO
  li t0,0x200000cf
  sd t0,16(t1)                 # identity SRAM/code superpage
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
  sd t0,32(t1)                 # read-only, store must fault before commit
  li t0,(0x80032000 >> 2) | 3
  sd t0,40(t1)                 # A=0, software will set it on fault
  li t0,(0x80034000 >> 2) | 0x5b
  sd t0,64(t1)                 # user R/X/A page, SUM required for S load
  li t0,(0x80035000 >> 2) | 0x59
  sd t0,72(t1)                 # user X/A page, MXR also required for load
  li t0,(0x80048000 >> 2) | 0xcf | (1 << 63)
  sd t0,88(t1)                 # 64 KiB NAPOT
  li t0,(0x80050000 >> 2) | 0xc7 | (1 << 61)
  sd t0,96(t1)                 # non-cacheable main memory
  li t0,0x80030000
  li t1,0x1122334455667788
  sd t1,0(t0)
  li t0,0x80031000
  li t1,0xdeadbeef01234567
  sd t1,0(t0)
  li t0,0x80032000
  li t1,0x3344
  sd t1,0(t0)
  li t0,0x80033000
  li t1,0x5566
  sd t1,0(t0)
  li t0,0x80034000
  li t1,0x7788
  sd t1,0(t0)
  li t0,0x80035000
  li t1,0x99aa
  sd t1,0(t0)
  li t0,0x8004b000
  li t1,0x1234abcd
  sd t1,0(t0)
  li t0,0x80050000
  li t1,0xabcd1234
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
  li t0,0xb000
  csrw medeleg,t0
  la t0,s_entry
  csrw mepc,t0
  li t0,0x800
  csrw mstatus,t0
  mret
s_entry:
  li a2,0
  li t0,0x40003000
  ld t1,0(t0)
  li t2,0x1122334455667788
  bne t1,t2,fail
  li t1,0x22334455
  sd t1,0(t0)
  ld t2,0(t0)
  bne t1,t2,fail
  li a0,1
  li t0,0x40004000
  sd zero,0(t0)
  li t0,0x80031000
  ld t1,0(t0)
  li t2,0xdeadbeef01234567
  bne t1,t2,fail
  li a0,2
  li s0,0x40005000
  ld s1,0(s0)
  li t0,0x3344
  bne s1,t0,fail
  li a0,3
  li t0,0x40006000
  ld zero,0(t0)
  li a0,4
  li t0,0x40007000
  jalr zero,0(t0)
resume_invalid_fetch:
  li a0,5
  li s0,0x40008000
  ld s1,0(s0)
  li t0,0x7788
  bne s1,t0,fail
  li a0,6
  li s0,0x40009000
  ld s1,0(s0)
  li t0,0x99aa
  bne s1,t0,fail
  li a0,7
  li t0,0x40008000
  jalr zero,0(t0)
resume_user_fetch:
  li t0,7
  bne a2,t0,fail
  # Change an already cached translation, drain PTE store, invalidate TLBs.
  la t0,level0
  li t1,(0x80033000 >> 2) | 0xc7
  sd t1,24(t0)
  li t0,0x40003000
  sfence.vma t0,zero
  ld t1,0(t0)
  li t2,0x5566
  bne t1,t2,fail
  li t0,0x4000b000
  ld t1,0(t0)
  li t2,0x1234abcd
  bne t1,t2,fail
  li t0,0x4000c000
  ld t1,0(t0)
  li t2,0xabcd1234
  bne t1,t2,fail
  addi t1,t1,1
  sd t1,0(t0)
  ld t2,0(t0)
  bne t1,t2,fail
  lui t0,0x10000
  li t1,0x53563339
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:wfi
  j 1b
s_trap:
  addi a2,a2,1
  csrr t4,scause
  csrr t5,stval
  li t6,1
  beq a0,t6,trap_store
  li t6,2
  beq a0,t6,trap_accessed
  li t6,3
  beq a0,t6,trap_invalid
  li t6,4
  beq a0,t6,trap_fetch
  li t6,5
  beq a0,t6,trap_sum
  li t6,6
  beq a0,t6,trap_mxr
  li t6,7
  beq a0,t6,trap_user_fetch
  j fail
trap_store:
  li t6,15
  bne t4,t6,fail
  li t6,0x40004000
  bne t5,t6,fail
  j skip_fault
trap_accessed:
  li t6,13
  bne t4,t6,fail
  li t6,0x40005000
  bne t5,t6,fail
  la t6,level0
  li t3,(0x80032000 >> 2) | 0x43
  sd t3,40(t6)
  sfence.vma
  sret
trap_invalid:
  li t6,13
  bne t4,t6,fail
  li t6,0x40006000
  bne t5,t6,fail
skip_fault:
  csrr t6,sepc
  addi t6,t6,4
  csrw sepc,t6
  sret
trap_fetch:
  li t6,12
  bne t4,t6,fail
  li t6,0x40007000
  bne t5,t6,fail
  la t6,resume_invalid_fetch
  csrw sepc,t6
  sret
trap_sum:
  li t6,13
  bne t4,t6,fail
  li t6,0x40008000
  bne t5,t6,fail
  li t6,0x40000
  csrs sstatus,t6
  sret
trap_mxr:
  li t6,13
  bne t4,t6,fail
  li t6,0x40009000
  bne t5,t6,fail
  li t6,0x80000
  csrs sstatus,t6
  sret
trap_user_fetch:
  li t6,12
  bne t4,t6,fail
  li t6,0x40008000
  bne t5,t6,fail
  la t6,resume_user_fetch
  csrw sepc,t6
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

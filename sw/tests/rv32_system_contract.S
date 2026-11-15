.section .text.init,"ax",@progbits
.option norvc
.option norelax
.globl _start
_start:
  csrci mstatus,8
  csrw mie,zero
  li t0,0x02000000
  sw zero,0(t0)
  la t0,handler
  csrw mtvec,t0
  li s0,0                    # interrupt count
  li s3,0                    # expected illegal-instruction count
  csrr t0,misa
  srli t0,t0,30
  li t1,1
  bne t0,t1,fail             # MXL must describe RV32
  .word 0x00003283           # RV64 LD is illegal in RV32
  .word 0x00003023           # RV64 SD is illegal in RV32
  .word 0x0000029b           # RV64 ADDIW is illegal in RV32
  li t0,3
  bne s3,t0,fail
  # Resolve a taken branch after a long producer; wrong-path store cannot commit.
  li t0,42
  li t1,1
  div t2,t0,t1
  beq t2,t0,correct_path
  li t0,0x10000000
  li t1,0xdead
  sw t1,0x14(t0)
correct_path:
  # The first call trains/fills both instruction paths. Patch the instruction
  # through the data path and require FENCE.I to expose the replacement.
  call patch_target
  li t0,1
  bne a0,t0,fail
  la t0,patch_target
  li t1,0x02a00513           # addi a0,zero,42
  sw t1,0(t0)
  fence rw,rw
  fence.i
  call patch_target
  li t0,42
  bne a0,t0,fail
  # Machine software interrupt.
  li t0,8
  csrw mie,t0
  csrsi mstatus,8
  li t0,0x02000000
  li t1,1
  sw t1,0(t0)
wait_msip:
  li t0,1
  bne s0,t0,wait_msip
  # Machine timer interrupt, compare zero is already in the past.
  li t0,0x02004000
  sw zero,0(t0)
  sw zero,4(t0)
  li t0,128
  csrw mie,t0
wait_mtip:
  li t0,2
  bne s0,t0,wait_mtip
  # External source 1 is driven by the testbench from HostIF flags[8].
  li t0,0x0c000000
  li t1,3
  sw t1,4(t0)
  li t1,2
  li t0,0x0c002000
  sw t1,0(t0)
  li t0,0x0c200000
  sw zero,0(t0)
  li t0,0x800
  csrw mie,t0
  li t0,0x10000000
  li t1,0x101
  sw t1,8(t0)
wait_meip:
  li t0,3
  bne s0,t0,wait_meip
  csrci mstatus,8
  csrw mie,zero
  li t0,0x800f0000
  li t1,0x51a7c0de
  sw t1,0(t0)
  sw zero,4(t0)
  li t0,0x10000000
  li t1,0x52563332
  sw t1,12(t0)
  sw zero,20(t0)
stop:
  j stop
.balign 64
patch_target:
  addi a0,zero,1
  ret
.balign 16
handler:
  csrr t0,mcause
  li t1,2
  beq t0,t1,illegal
  li t1,0x80000003
  beq t0,t1,software
  li t1,0x80000007
  beq t0,t1,timer
  li t1,0x8000000b
  beq t0,t1,external
  j fail
illegal:
  addi s3,s3,1
  csrr t0,mepc
  addi t0,t0,4
  csrw mepc,t0
  mret
software:
  bnez s0,fail
  li t0,0x02000000
  sw zero,0(t0)
  addi s0,s0,1
  mret
timer:
  li t0,1
  bne s0,t0,fail
  li t0,0x02004000
  li t1,-1
  sw t1,4(t0)
  sw t1,0(t0)
  addi s0,s0,1
  mret
external:
  li t0,2
  bne s0,t0,fail
  li t0,0x0c200004
  lw t1,0(t0)
  li t2,1
  bne t1,t2,fail
  li t2,0x10000000
  li t1,0x201
  sw t1,8(t2)               # deassert source before completion
  li t1,1
  sw t1,0(t0)
  addi s0,s0,1
  mret
fail:
  csrci mstatus,8
  li t0,0x10000000
  li t1,1
  sw t1,20(t0)
  j fail

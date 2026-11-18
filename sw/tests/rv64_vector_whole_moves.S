.section .text.init,"ax"
.option norvc
.option norelax
.globl _start

.macro move registers, bits, start, mode=0
  vl8re8.v v16,(s1)
  .if \mode == 2
    li t0,-1
    li t1,0
    vsetvl zero,t1,t0
    csrr t0,vtype
    bgez t0,fail
  .else
    vsetivli zero,0,e\bits,m1,tu,mu
  .endif
  li t0,\start
  csrw vstart,t0
  .if \mode
    la s6,5f
  .endif
  vmv\registers\()r.v v16,v8
  li s6,0
  csrr t0,vstart
  bnez t0,fail
  csrr t0,vl
  bnez t0,fail
  vs8r.v v16,(s2)
  li a0,(\start * \bits / 8)
  li a1,(\registers * 16)
  jal ra,check_bytes
  .if \mode
    j 6f
5:
    li s6,0
    csrw vstart,zero
    vs8r.v v16,(s2)
    li a0,128
    li a1,0
    jal ra,check_bytes
6:
  .endif
.endm

_start:
  la t0,trap
  csrw mtvec,t0
  li t0,0x600
  csrs mstatus,t0
  la s0,values
  la s1,sentinel
  la s2,result
  li s6,0
  vl8re8.v v8,(s0)
  .irp registers,1,2,4,8
    .irp bits,8,16,32,64
      move \registers,\bits,0
      move \registers,\bits,(\registers * 64 / \bits)
      move \registers,\bits,(\registers * 128 / \bits - 1)
    .endr
  .endr

  # Trace marker separating shared behavior from reference limitations.
  addi zero,zero,123
  .irp registers,1,2,4,8
    .irp bits,8,16,32,64
      .if (\registers * 128 / \bits) < 128
        move \registers,\bits,(\registers * 128 / \bits),1
      .endif
    .endr
    move \registers,8,0,2
  .endr
  li t1,1
  j finish

check_bytes:
  li t0,0
  li t3,128
  li t4,0xa5
  mv t5,s2
next_byte:
  lbu t1,0(t5)
  mv t2,t4
  bltu t0,a0,compare_byte
  bgeu t0,a1,compare_byte
  addi t2,t0,1
compare_byte:
  bne t1,t2,fail
  addi t0,t0,1
  addi t5,t5,1
  bltu t0,t3,next_byte
  ret

trap:
  beqz s6,fail
  csrr t0,mcause
  li t1,2
  bne t0,t1,fail
  csrw mepc,s6
  mret

fail:
  li t1,3
finish:
  la t0,tohost
  sd t1,0(t0)
1: j 1b

.section .tohost,"aw"
.balign 8
.globl tohost,fromhost
tohost: .dword 0
fromhost: .dword 0

.section .rodata
.balign 16
values:
  .set byte_value,1
  .rept 128
    .byte byte_value
    .set byte_value,byte_value+1
  .endr
sentinel: .fill 128,1,0xa5

.section .bss
.balign 16
result: .space 128

.section .text.init,"ax"
.option norvc
.option norelax
.globl _start

.equ base, 0x800a0000
.equ alias_a, 0x400a0000
.equ alias_b, 0x402a0000
.equ initial_a, 0x0102030405060708
.equ initial_b, 0x9192939495969798
.equ vector_a, 0x1122334455667788
.equ vector_b, 0x99aabbccddeeff00
.equ guard, 0xbabefeeddeadbeef

_start:
  la t0,fail
  csrw mtvec,t0
  csrw stvec,t0
  li t0,-1
  csrw pmpaddr0,t0
  li t0,31
  csrw pmpcfg0,t0
  li t0,0x600
  csrs mstatus,t0
  li s0,base
  mv s1,s0
  jal ra,exercise_offsets

  # Map both S-mode aliases onto the same writable SRAM megapage.
  la t0,root
  la t1,level1
  srli t1,t1,2
  ori t1,t1,1
  sd t1,8(t0)
  li t1,(0x80000000 >> 2) | 0xcf
  sd t1,16(t0)                 # Identity map for S-mode code.
  la t0,level1
  sd t1,0(t0)
  sd t1,8(t0)
  la t0,root
  srli t0,t0,12
  li t1,0x8000000000000000
  or t0,t0,t1
  csrw satp,t0
  sfence.vma
  la t0,supervisor
  csrw mepc,t0
  li t0,0xe00
  csrw mstatus,t0
  mret

supervisor:
  li s0,alias_a
  li s1,alias_b
  jal ra,exercise_offsets
  li t1,1
  j finish

exercise_offsets:
  mv s5,ra
  .irp offset,0,8,48,56
    addi s2,s0,\offset
    addi s3,s1,\offset
    jal ra,exercise
  .endr
  jr s5

exercise:
  vsetivli zero,2,e64,m1,tu,mu
  li t0,guard
  sd t0,-8(s2)
  sd t0,16(s2)
  li t0,initial_a
  sd t0,0(s2)
  li t1,initial_b
  sd t1,8(s2)
  vle64.v v8,(s3)
  vmv.x.s a0,v8
  bne a0,t0,fail
  vslidedown.vi v9,v8,1
  vmv.x.s a0,v9
  bne a0,t1,fail

  li t0,vector_a
  li t1,vector_b
  vmv.v.x v10,t0
  vslide1down.vx v11,v10,t1
  vse64.v v11,(s3)
  ld a0,0(s2)
  bne a0,t0,fail
  ld a0,8(s2)
  bne a0,t1,fail

  li t0,0xab
  sb t0,1(s2)
  li t0,0xcdef
  sh t0,6(s2)
  li t0,0x01234567
  sw t0,12(s2)
  vle64.v v8,(s3)
  li t0,0xcdef33445566ab88
  li t1,0x01234567ddeeff00
  vmv.x.s a0,v8
  bne a0,t0,fail
  vslidedown.vi v9,v8,1
  vmv.x.s a0,v9
  bne a0,t1,fail

  li t2,1
  amoadd.d a0,t2,(s2)
  bne a0,t0,fail
  addi t0,t0,1
  vle64.v v8,(s3)
  vmv.x.s a0,v8
  bne a0,t0,fail
  vslidedown.vi v9,v8,1
  vmv.x.s a0,v9
  bne a0,t1,fail
  ld a0,-8(s3)
  li t0,guard
  bne a0,t0,fail
  ld a0,16(s3)
  bne a0,t0,fail
  ret

fail:
  li t1,3
finish:
  la t0,tohost
  sd t1,0(t0)
halt:
  j halt

.section .tohost,"aw"
.balign 8
.globl tohost,fromhost
tohost: .dword 0
fromhost: .dword 0

.section .bss
.balign 4096
root: .space 4096
level1: .space 4096

.section .text
.global _start
_start:
  la t0, scratch
  li t1, 0x12345678
  sw t1, 0(t0)
  lw t2, 0(t0)
  bne t1,t2,fail
  li t1,0xaa
  sb t1,1(t0)
  lhu t2,0(t0)
  li t1,0xaa78
  bne t1,t2,fail
  fence rw,rw
  fence.i
  li t0,0x02000000
  li t1,1
  sw t1,0(t0)
  lw t2,0(t0)
  bne t1,t2,fail
  sw zero,0(t0)
  la t0,done
  li t1,0x600d
  sw t1,0(t0)
wait:
  j wait
fail:
  la t0,done
  li t1,0xbad
  sw t1,0(t0)
  j fail
.section .data
.balign 64
scratch: .word 0
.balign 8
done: .word 0
.word 0

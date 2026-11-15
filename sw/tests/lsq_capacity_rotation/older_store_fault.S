/* Directed precise-exception/LQ-pressure test, NOT RISC-V DV.
 * 256 older misaligned stores must trap; younger loads must not retire until
 * recovery. mret skips only the faulting store. All6144 loads then check the
 * older legal value, proving the faulting store did not become visible.
 * Default TIM/CLINT and structured HostIF; no C ABI stack is used.
 */
#ifndef LSQ_FAULT_EXPECTED_CAUSE
#define LSQ_FAULT_EXPECTED_CAUSE 6
#endif
  .section .text.init,"ax",@progbits
  .option norvc
  .option norelax
  .globl _start
_start:
  li x1,0x02000000
  sw zero,0(x1)
  csrw mie,zero
  csrci mstatus,8
  la x1,handler
  csrw mtvec,x1
  li x1,0x8003ff00
  csrw mscratch,x1
  la x5,test_data
  li x2,128
  li x1,0x10000000
  li x6,0x50460001
  sw x6,0x0c(x1)

  .macro fault_pressure stride
  li x1,0xdeadbeef
  sw x1,0(x5)
  li x4,0x60001000
  xor x4,x4,x2
  li x3,0x7ffffffd
  li x6,3
  divu x7,x3,x6
  or x7,x7,x3
  divu x7,x7,x6
  andi x7,x7,0
  add x7,x7,x5
  addi x7,x7,1
  la x6,fault_site\@
fault_site\@:
  sw x4,0(x7)
  .set off,0
  .irp dst,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31
    lw x\dst,off(x5)
    .set off,off+\stride
  .endr
  li x6,0xdeadbeef
  bne x8,x6,fail
  .set off,\stride
  .irp dst,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31
    li x6,(0x1000+(off/4)*17)
    bne x\dst,x6,fail
    .set off,off+\stride
  .endr
  .endm

again:
  fault_pressure 4
  fault_pressure 8
  addi x2,x2,-1
  bnez x2,again
  la x1,trap_count
  lw x6,0(x1)
  li x1,256
  bne x6,x1,fail
  li x1,0x10000000
  li x6,0x50460002
  sw x6,0x0c(x1)
  li x6,0x4c535146
  sw x6,0x0c(x1)
  sw zero,0x14(x1)
1: wfi
  j 1b

  .balign 4
handler:
  # Preserve the only two GPRs touched by this handler. x2 is a loop counter,
  # not a usable stack; mscratch holds a dedicated valid DTIM scratch slot.
  csrrw x1,mscratch,x1
  sw x6,0(x1)
  csrr x6,mcause
  addi x6,x6,-LSQ_FAULT_EXPECTED_CAUSE
  bnez x6,fail
  csrr x6,mtval
  bne x6,x7,fail
  lw x1,0(x1)
  csrr x6,mepc
  bne x1,x6,fail
  addi x6,x6,4
  csrw mepc,x6
  la x1,trap_count
  lw x6,0(x1)
  addi x6,x6,1
  sw x6,0(x1)
  li x1,0x8003ff00
  lw x6,0(x1)
  csrrw x1,mscratch,x1
  mret

fail:
  li x1,0x10000000
  li x6,0xdeadf006
  sw x6,0x0c(x1)
  li x6,1
  sw x6,0x14(x1)
2: wfi
  j 2b

  .section .data,"aw",@progbits
  .balign 16
test_data:
  .set wordno,0
  .rept 48
    .word 0x1000+wordno*17
    .set wordno,wordno+1
  .endr
trap_count:
  .word 0

.section .text.init,"ax"
.option norvc
.option norelax
.globl _start
_start:
  la t0,handler
  csrw mtvec,t0
  li t0,0x6600
  csrs mstatus,t0
  la s0,guard
  la s7,pending_data
  li s1,0x0200bff8
  li s2,100
  li s3,7
  li s6,0
  li t4,0x4008000000000000
  vsetivli zero,2,e64,m1,tu,mu
  vmv.v.x v16,s2
  vmv.v.x v24,s3

  # An independent FP result must execute while DIV owns the vector head,
  # then retire correctly in lane 1 beside that vector instruction.
.globl overlap_div,overlap_fp
overlap_div:
  vdivu.vv v8,v16,v24
overlap_fp:
  fmv.d.x ft1,t4
  addi a2,zero,1234
  vmv.x.s a0,v8
  addi a1,a0,1
  li t0,14
  bne a0,t0,fail
  li t0,15
  bne a1,t0,fail
  li t0,1234
  bne a2,t0,fail
  fmv.x.d t0,ft1
  bne t0,t4,fail

  # Scalar WAW retains the younger mapping, including a vector scalar result.
  vmv.x.s a0,v8
  li a0,99
  li t0,99
  bne a0,t0,fail
  addi a3,zero,44
  vmv.v.x v9,a3
  vmv.x.s t0,v9
  bne t0,a3,fail

  # A vector scalar result used as a load base is already in the IQ before
  # system-result wakeup. Its cached address must receive the result value.
  la t0,pointer_value
  vmv.v.x v13,t0
  vmv.x.s t3,v13
  ld t2,0(t3)
  li t1,0x3456789abcdef012
  bne t1,t2,fail

  # Source capture must read the old physical FP mapping, while the younger
  # FP write may finish early and co-retire with the vector move.
  li t0,0x4000000000000000
  fmv.d.x fa0,t0
  vfmv.v.f v12,fa0
  fmv.d.x fa0,t4
  vmv.x.s t1,v12
  li t0,0x4000000000000000
  bne t0,t1,fail
  fmv.x.d t0,fa0
  bne t0,t4,fail

  # The scalar divide lets a younger cold SRAM load enter the memory engine.
  # VADD can begin before that refill completes. Ordered MMIO remains held
  # until its own turn at head; queued MMIO alone does not lower memory_idle.
  .balign 64
  divu a5,s2,s3
  vadd.vv v8,v16,v24
  ld zero,0(s7)
  ld zero,0(s1)
  vmv.x.s t0,v8
  li t1,107
  bne t0,t1,fail

  # Younger branch recovery must preserve an accepted older vector owner.
  vdivu.vv v8,v16,v24
  beq zero,zero,branch_safe
  li a4,777
  sd t4,0(s0)
  j fail
branch_safe:
  vmv.x.s t0,v8
  li t1,14
  bne t0,t1,fail
  ld t0,0(s0)
  li t1,0x123456789abcdef0
  bne t0,t1,fail

  # Illegal destination grouping traps at head. All younger scalar/FP/store
  # effects are discarded before returning directly to after_bad.
  li a4,88
  li t0,0x4014000000000000
  fmv.d.x ft2,t0
  vsetivli zero,8,e64,m8,tu,mu
.globl bad_vector
bad_vector:
  vadd.vv v1,v16,v24
  li a4,777
  fmv.d.x ft2,t4
  sd t4,0(s0)
  j fail
after_bad:
  li t0,1
  bne s6,t0,fail
  li t0,88
  bne a4,t0,fail
  fmv.x.d t0,ft2
  li t1,0x4014000000000000
  bne t0,t1,fail
  ld t0,0(s0)
  li t1,0x123456789abcdef0
  bne t0,t1,fail
  li t1,1
  j finish
handler:
  csrr t0,mcause
  li t1,2
  bne t0,t1,fail
  csrr t0,mepc
  la t1,bad_vector
  bne t0,t1,fail
  addi s6,s6,1
  la t0,after_bad
  csrw mepc,t0
  mret
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
.section .data,"aw"
.balign 64
guard: .dword 0x123456789abcdef0
.balign 64
pending_data: .dword 0x23456789abcdef01
.balign 64
pointer_value: .dword 0x3456789abcdef012

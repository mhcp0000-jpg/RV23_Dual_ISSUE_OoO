.section .text.init,"ax"
.option norvc
.globl _start
_start:
  lui t0,0x02000
  sw zero,0(t0)
  la t0,m_trap
  csrw mtvec,t0
  la s0,buffer
  la sp,stack_top
  li s6,0
  li t0,0x2000                 # FS=Initial, no eager Dirty on state enable
  csrw mstatus,t0
  csrr t0,mstatus
  srli t0,t0,13
  andi t0,t0,3
  li t1,1
  bne t0,t1,fail
  li t0,0x0123456789abcdef
  fmv.d.x ft0,t0
  csrr t1,mstatus
  bgez t1,fail                 # SD must reflect Dirty on RV64
  srli t1,t1,13
  andi t1,t1,3
  li t2,3
  bne t1,t2,fail
  fsd ft0,0(s0)
  ld t1,0(s0)
  bne t0,t1,fail
  fld ft1,0(s0)
  fmv.x.d t1,ft1
  bne t0,t1,fail
  li t0,0x3f800000
  sw t0,16(s0)
  flw ft2,16(s0)               # both forwarding and cache-return paths box
  fmv.x.d t1,ft2
  li t2,0xffffffff3f800000
  bne t1,t2,fail
  fence rw,rw
  flw ft3,16(s0)
  fmv.x.d t1,ft3
  bne t1,t2,fail
  li t0,0x3c00
  sh t0,24(s0)
  flh ft4,24(s0)
  fmv.x.d t1,ft4
  li t2,0xffffffffffff3c00
  bne t1,t2,fail
  fence rw,rw
  flh ft5,24(s0)
  fmv.x.d t1,ft5
  bne t1,t2,fail
  fcvt.d.h ft6,ft4
  fmv.x.d t1,ft6
  li t2,0x3ff0000000000000
  bne t1,t2,fail
  li t0,-1
  sd t0,32(s0)
  fsh ft4,34(s0)
  fsw ft2,36(s0)
  ld t1,32(s0)
  li t2,0x3f8000003c00ffff
  bne t1,t2,fail
  # All four compressed D forms, including legal f0 at SP and prime regs.
  .option rvc
  c.fsdsp ft6,0(sp)
  c.fldsp ft0,0(sp)
  c.fsd fs0,0(s0)
  c.fld fs1,0(s0)
  .option norvc
  fmv.x.d t1,ft0
  li t2,0x3ff0000000000000
  bne t1,t2,fail
  fmv.d fs0,ft0
  .option rvc
  c.fsd fs0,0(s0)
  c.fld fs1,0(s0)
  .option norvc
  fmv.x.d t1,fs1
  bne t1,t2,fail
  # Classification with integer destination and no flags may leave FS Clean.
  csrw fcsr,zero
  li t0,0x4000
  csrw mstatus,t0
  fclass.d t1,ft0
  li t2,64
  bne t1,t2,fail
  csrr t0,mstatus
  srli t0,t0,13
  andi t0,t0,3
  li t1,2
  bne t0,t1,fail
  csrw fflags,zero             # an explicit FCSR write does dirty FS
  csrr t0,mstatus
  bgez t0,fail
  # A flag update from an integer-result compare also dirties state.
  li t0,0x7ff0000000000001
  fmv.d.x ft1,t0
  li t0,0x4000
  csrw mstatus,t0
  feq.d t1,ft1,ft0
  csrr t0,mstatus
  bgez t0,fail
  csrr t0,fflags
  li t1,16
  bne t0,t1,fail
  csrw fcsr,zero
  # FS Off blocks arithmetic, loads, stores, raw moves, and FCSR reads.
  csrw mstatus,zero
  la t0,off_add
  lwu a4,0(t0)
off_add:
  fadd.d ft2,ft0,ft0
  la t0,off_load
  lwu a4,0(t0)
off_load:
  fld ft2,0(s0)
  la t0,off_store
  lwu a4,0(t0)
off_store:
  fsd ft1,0(s0)
  la t0,off_move
  lwu a4,0(t0)
off_move:
  fmv.x.d t0,ft0
  la t0,off_csr
  lwu a4,0(t0)
off_csr:
  csrr t0,fcsr
  li t0,0x6000
  csrw mstatus,t0
  fld ft2,0(s0)                # denied store must not have changed memory
  fmv.x.d t1,ft2
  li t2,0x3ff0000000000000
  bne t1,t2,fail
  # Reserved static/dynamic rounding modes, original instruction in mtval.
  li a4,0x02005153
  .word 0x02005153
  li t0,5
  csrw frm,t0
  li a4,0x02007153
  .word 0x02007153
  csrr t0,fflags
  bnez t0,fail
  li t0,7
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x46505354
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:j 1b
m_trap:
  csrr t4,mcause
  li t5,2
  bne t4,t5,fail
  csrr t4,mtval
  bne t4,a4,fail
  addi s6,s6,1
  csrr t4,mepc
  addi t4,t4,4
  csrw mepc,t4
  mret
fail:
  lui t0,0x10000
  li t1,1
  sw t1,0x14(t0)
  j 1b
.section .data,"aw"
.balign 64
buffer:.zero 128
stack:.zero 128
stack_top:.zero 16

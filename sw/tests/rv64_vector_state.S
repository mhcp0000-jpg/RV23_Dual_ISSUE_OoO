.section .text.init,"ax"
.option norvc
.globl _start
.macro illegal insn:vararg
  li a6,1
  \insn
  bnez a6,fail
.endm
_start:
  lui t0,0x02000
  sw zero,0(t0)
  la t0,m_trap
  csrw mtvec,t0
  li s6,0
  li s7,0
  csrw mstatus,zero
  illegal vsetivli a0,4,e32,m1,tu,mu
  illegal csrr a0,vlenb
  illegal csrw vstart,zero
  li t0,0x200
  csrw mstatus,t0
  csrr t0,mstatus
  bltz t0,fail
  srli t0,t0,9
  andi t0,t0,3
  li t1,1
  bne t0,t1,fail
  csrr t0,misa
  li t1,1<<21
  and t0,t0,t1
  beqz t0,fail
  csrr t0,vlenb
  li t1,16
  bne t0,t1,fail
  csrr t0,vtype
  bgez t0,fail
  vsetivli a0,4,e32,m1,tu,mu
  li t1,4
  bne a0,t1,fail
  csrr t0,mstatus
  bgez t0,fail
  srli t0,t0,9
  andi t0,t0,3
  li t1,3
  bne t0,t1,fail
  vmv.v.i v1,1
  vadd.vi v2,v1,7
  vmv.x.s t0,v2
  li t1,8
  bne t0,t1,fail
  csrr t0,mstatus
  srli t0,t0,13
  andi t0,t0,3
  bnez t0,fail
  illegal vfadd.vv v3,v1,v2
  illegal csrr t0,fflags
  li s7,1
  li t0,0x2000
  csrs mstatus,t0
  li a0,0x3f800000
  vmv.v.x v1,a0
  vfadd.vv v2,v1,v1
  vmv.x.s t0,v2
  li t1,0x40000000
  bne t0,t1,fail
  csrr t0,fflags
  bnez t0,fail
  vmv.v.i v3,0
  vfdiv.vv v4,v1,v3
  csrr t0,fflags
  li t1,8
  bne t0,t1,fail
  csrr t0,mstatus
  srli t0,t0,13
  andi t0,t0,3
  li t1,3
  bne t0,t1,fail
  li t0,0x2400                 # VS=Clean, FS=Initial
  csrw mstatus,t0
  li t0,127
  csrw vstart,t0
  csrr t1,vstart
  bne t0,t1,fail
  csrr t0,mstatus
  srli t0,t0,9
  andi t0,t0,3
  li t1,3
  bne t0,t1,fail
  vadd.vi v2,v1,1              # start>=vl: destination remains 2.0
  csrr t0,vstart
  bnez t0,fail
  vmv.x.s t0,v2
  li t1,0x40000000
  bne t0,t1,fail
  li t0,7
  csrw vcsr,t0
  csrr t1,vcsr
  bne t0,t1,fail
  csrr t1,vxrm
  li t0,3
  bne t0,t1,fail
  csrr t1,vxsat
  li t0,1
  bne t0,t1,fail
  csrw vcsr,zero
  illegal csrw vl,zero
  illegal csrw vtype,zero
  illegal csrw vlenb,zero
  li s7,2
  li t0,5
  csrw frm,t0
  illegal vfadd.vv v3,v1,v2
  vsetivli zero,0,e32,m1,tu,mu
  illegal vfadd.vv v3,v1,v2   # reserved FRM is checked even for vl=0
  vid.v v4                    # integer operations ignore FRM
  csrw frm,zero
  vsetivli zero,4,e32,m1,tu,mu
  csrw mstatus,zero
  illegal vmv.x.s t0,v2
  li t0,0x2200
  csrw mstatus,t0
  vmv.x.s t0,v2               # disabling VS preserves register payload
  li t1,0x40000000
  bne t0,t1,fail
  li t0,11
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x56535431
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:j 1b
m_trap:
  beqz a6,fail
  csrr t4,mcause
  li t5,2
  bne t4,t5,fail
  csrr t4,mepc
  lwu t5,0(t4)
  csrr t3,mtval
  bne t5,t3,fail
  addi t4,t4,4
  csrw mepc,t4
  li a6,0
  addi s6,s6,1
  mret
fail:
  lui t0,0x10000
  sw s7,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j 1b

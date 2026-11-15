s_entry:
  li s0,0x40003000
  fld ft0,0(s0)
  fmv.x.d t1,ft0
  li t2,10
  bne t1,t2,fail
  li t0,0x0123456789abcdef
  fmv.d.x ft1,t0
  fsd ft1,8(s0)
  ld t1,8(s0)
  bne t1,t0,fail
  flw ft2,8(s0)
  fmv.x.d t1,ft2
  li t2,0xffffffff89abcdef
  bne t1,t2,fail
  flh ft3,8(s0)
  fmv.x.d t1,ft3
  li t2,0xffffffffffffcdef
  bne t1,t2,fail
  # FP stores must check PTE W and D before any architectural write.
  li s1,0x40004000
  li a4,15
  mv a5,s1
  fsd ft1,0(s1)
  fsw ft1,0(s1)
  fsh ft1,0(s1)
  li s1,0x80031000
  ld t1,0(s1)
  li t2,0x123456789abcdef0
  bne t1,t2,fail
  li s1,0x40005000
  mv a5,s1
  fsd ft1,0(s1)               # D=0 with W=1
  li s1,0x80032000
  ld t1,0(s1)
  li t2,20
  bne t1,t2,fail
  li s1,0x40006000
  li a4,13
  mv a5,s1
  fld ft4,0(s1)
  flw ft4,0(s1)
  flh ft4,0(s1)
  li s1,0x40008000
  mv a5,s1
  fld ft4,0(s1)               # U page, SUM=0
  li t0,0x40000
  csrs sstatus,t0
  fld ft4,0(s1)
  fmv.x.d t1,ft4
  li t2,20
  bne t1,t2,fail
  li s1,0x4000c000
  fsd ft1,0(s1)               # NC page: same memory format semantics
  fld ft5,0(s1)
  fmv.x.d t1,ft5
  li t2,0x0123456789abcdef
  bne t1,t2,fail
  li t0,8
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x4650564d
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:wfi
  j 1b

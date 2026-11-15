s_entry:
  li s0,0x40003ffd
  ld t1,0(s0)                 # two nonadjacent physical pages
  li t2,0x5544332211112233
  bne t1,t2,fail
  li t0,0x0123456789abcdef
  sd t0,0(s0)
  ld t1,0(s0)
  bne t1,t0,fail
  fld ft0,0(s0)
  fmv.x.d t1,ft0
  bne t1,t0,fail
  li s1,0x80030ff8
  ld t1,0(s1)
  li t2,0xabcdef4455667788
  bne t1,t2,fail
  li s1,0x80036000
  ld t1,0(s1)
  li t2,0x8877660123456789
  bne t1,t2,fail
  # Every byte's translation/PMP check must finish before any byte is written.
  la s2,level0
  li t0,(0x80036000 >> 2) | 0x43
  sd t0,32(s2)
  sfence.vma
  li a4,15
  li a5,0x40004000
  sd zero,0(s0)               # second page read-only
  li t0,(0x80036000 >> 2) | 0x47
  sd t0,32(s2)
  sfence.vma
  fsd ft0,0(s0)               # second page D=0
  li s1,0x80030ff8
  ld t1,0(s1)
  li t2,0xabcdef4455667788
  bne t1,t2,fail
  li s1,0x80036000
  ld t1,0(s1)
  li t2,0x8877660123456789
  bne t1,t2,fail
  sd zero,32(s2)
  sfence.vma
  li a4,13
  fld ft0,0(s0)               # invalid second page leaves FP dest unchanged
  fmv.x.d t1,ft0
  li t2,0x0123456789abcdef
  bne t1,t2,fail
  li t0,(0x80036000 >> 2) | 0xc7 | (1 << 62)
  sd t0,32(s2)
  sfence.vma
  li a4,7
  sd zero,0(s0)               # PBMT IO forbids this main-memory assist
  li a4,5
  ld zero,0(s0)
  li s1,0x80030ff8
  ld t1,0(s1)
  li t2,0xabcdef4455667788
  bne t1,t2,fail
  li t0,5
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x4d495356
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:wfi
  j 1b

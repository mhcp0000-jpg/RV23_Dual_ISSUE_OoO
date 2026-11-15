.section .text.init,"ax"
.option norvc
.option norelax
.globl _start

.macro expect value
  li t1,\value
  bne t0,t1,fail
.endm

.macro illegal word, start
  li s0,\word
  li s1,\start
  csrw vstart,s1
  .word \word
  bnez s0,fail
  csrr t0,vstart
  bne t0,s1,fail
  csrw vstart,zero
.endm

_start:
  la t0,trap
  csrw mtvec,t0
  li t0,0x6600
  csrs mstatus,t0
  li s0,0
  li s2,0

#ifndef MIXED_EEW_HTIF
  # An m1 source may overlap the upper half of its m2 destination.
  vsetivli zero,16,e8,m1,tu,mu
  vid.v v9
  vmv.v.i v8,11
  li a0,255
  vwaddu.vx v8,v9,a0
  vsetivli zero,16,e16,m2,tu,mu
  vmv.x.s t0,v8
  expect 255
  vslidedown.vi v16,v8,8
  vmv.x.s t0,v16
  expect 263
  vslidedown.vi v16,v8,15
  vmv.x.s t0,v16
  expect 270

  # An m1 destination may overlap the lower half of its m2 source.
  # Restart leaves the first output byte undisturbed.
  vsetivli zero,16,e8,m1,tu,mu
  csrwi vstart,1
  vnsrl.wi v8,v8,1
  csrr t0,vstart
  expect 0
  vmv.x.s t0,v8
  expect -1
  vslidedown.vi v16,v8,1
  vmv.x.s t0,v16
  expect -128
  vslidedown.vi v16,v8,15
  vmv.x.s t0,v16
  expect -121

  # Mask EEW=1 may overlap the lowest register of the source.
  # Restart reads source elements from v9 and updates mask bits in v8.
  li t0,32
  vsetvli zero,t0,e8,m2,tu,mu
  vid.v v8
  li a0,20
  csrwi vstart,17
  vmsltu.vx v8,v8,a0
  csrr t0,vstart
  expect 0
  vsetivli zero,2,e64,m1,tu,mu
  vmv.x.s t0,v8
  expect 0x07060504000e0100
  vslidedown.vi v16,v8,1
  vmv.x.s t0,v16
  expect 0x0f0e0d0c0b0a0908

  vsetivli zero,8,e8,m1,tu,mu
  illegal 0xc2856457,3        # vwaddu.vx v8,v8,a0
  illegal 0xb280b4d7,2        # vnsrl.wi v9,v8,1
  illegal 0x3a880457,1        # vrgatherei16.vv v8,v8,v16
  illegal 0x5e842457,0        # vcompress.vm v8,v8,v8
  illegal 0x5e802657,1        # vcompress.vm v12,v8,v0 with nonzero vstart
  illegal 0x02822657,1        # vredsum.vs v12,v8,v4 with nonzero vstart
  vsetivli zero,8,e8,mf2,tu,mu
  illegal 0xc2856457,3        # fractional source cannot overlap when widening
  vsetivli zero,2,e64,m1,tu,mu
  vmv.x.s t0,v8
  expect 0x07060504000e0100
  vslidedown.vi v16,v8,1
  vmv.x.s t0,v16
  expect 0x0f0e0d0c0b0a0908
#endif

  # Preserve nonzero vstart when mixed-EEW sources alias.
  vsetivli zero,4,e16,m1,tu,mu
  illegal 0xd284a857,1        # vwaddu.wv v16,v8,v9
  illegal 0xb2848a57,1        # vnsrl.wv v20,v8,v9
  vsetivli zero,4,e8,m1,tu,mu
  illegal 0x3a940a57,1        # vrgatherei16.vv v20,v9,v8
  illegal 0x5e842a57,0        # vcompress.vm v20,v8,v8
  vsetivli zero,4,e8,m2,tu,mu
  illegal 0xc2848a57,0        # vwredsumu.vs v20,v8,v9
  vsetivli zero,4,e32,m1,tu,mu
  illegal 0xd2849857,1        # vfwadd.wv v16,v8,v9

  vsetivli zero,4,e16,m1,tu,mu
  li a1,0x80070000
  sd zero,(a1)
  vmv.v.i v10,3
  vmv.v.i v11,0
  illegal 0x26b58527,1        # vsuxseg2ei8.v v10,(a1),v11
  ld t0,(a1)
  expect 0
  vmv.v.i v10,2
  vadd.vv v20,v10,v10
  vmv.x.s t0,v20
  expect 4
  vsuxei16.v v10,(a1),v10
  lhu t0,2(a1)
  expect 2
  mv t0,s2
#ifdef MIXED_EEW_HTIF
  expect 7
  li t1,1
  j finish
#else
  expect 14
  lui t0,0x10000
  li t1,0x564f4c50
  sw t1,0xc(t0)
  sw zero,0x14(t0)
#endif
halt:
  j halt
trap:
  beqz s0,fail
  csrr t0,mcause
  expect 2
  csrr t0,mtval
  bne t0,s0,fail
  csrr t0,mepc
  lwu t1,0(t0)
  bne t1,s0,fail
  addi t0,t0,4
  csrw mepc,t0
  li s0,0
  addi s2,s2,1
  mret
fail:
#ifdef MIXED_EEW_HTIF
  li t1,3
finish:
  la t0,tohost
  sd t1,0(t0)
  j halt

.section .tohost,"aw"
.balign 8
.globl tohost,fromhost
tohost: .dword 0
fromhost: .dword 0
#else
  lui t0,0x10000
  li t1,1
  sw t1,0x14(t0)
  j halt
#endif

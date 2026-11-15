s_entry:
  li a6,0
  li s0,0x40003ff0
  li a0,4
  vsetvli t0,a0,e64,m2,tu,mu
  li t1,4
  bne t0,t1,fail
  vle64.v v8,(s0)
  vmv.x.s t0,v8
  li t1,11
  bne t0,t1,fail
  vslidedown.vi v24,v8,1
  vmv.x.s t0,v24
  li t1,22
  bne t0,t1,fail
  vslidedown.vi v24,v8,2
  vmv.x.s t0,v24
  li t1,33
  bne t0,t1,fail
  vslidedown.vi v24,v8,3
  vmv.x.s t0,v24
  li t1,44
  bne t0,t1,fail

  # W=0 on the second page: trap after two completed elements. The handler
  # changes those earlier physical words, repairs the PTE, and retries at
  # the SAME instruction. Correct vstart replay must preserve those changes.
  la t0,level0
  li t1,(0x80036000 >> 2) | 0x43
  sd t1,32(t0)
  sfence.vma
  li a4,15
  li a5,0x40004000
  li a7,2
  li a6,1
  li a0,99
  vmv.v.x v8,a0
  vse64.v v8,(s0)
  csrr t0,vstart
  bnez t0,fail
  li t0,0x80030ff0
  ld t1,0(t0)
  li t2,111
  bne t1,t2,fail
  ld t1,8(t0)
  li t2,222
  bne t1,t2,fail
  li t0,0x80036000
  ld t1,0(t0)
  li t2,99
  bne t1,t2,fail
  ld t1,8(t0)
  bne t1,t2,fail
  li t0,1
  bne s6,t0,fail

  # Invalid second page: preserve old destination elements at and after the
  # fault. Handler skips this instruction, leaving vstart available to SW.
  li a6,0
  la t0,level0
  sd zero,32(t0)
  sfence.vma
  vmv.v.i v8,7
  li a4,13
  vle64.v v8,(s0)
  csrr t0,vstart
  li t1,2
  bne t0,t1,fail
  csrw vstart,zero
  vmv.x.s t0,v8
  li t1,111
  bne t0,t1,fail
  vslidedown.vi v24,v8,1
  vmv.x.s t0,v24
  li t1,222
  bne t0,t1,fail
  vslidedown.vi v24,v8,2
  vmv.x.s t0,v24
  li t1,7
  bne t0,t1,fail
  vslidedown.vi v24,v8,3
  vmv.x.s t0,v24
  bne t0,t1,fail
  vle64ff.v v8,(s0)
  csrr t0,vl
  li t1,2
  bne t0,t1,fail
  csrr t0,vstart
  bnez t0,fail
  li a0,4
  vsetvli zero,a0,e64,m2,tu,mu
  li t0,0x40003ffc
  li a7,0
  vle64ff.v v8,(t0)            # first split element faults at second page
  csrr t0,vl
  li t1,4
  bne t0,t1,fail

  # Natural PBMT IO elements are complete-size, uncached bus accesses. A
  # split element entering IO is denied before any part of that element.
  la t0,level0
  li t1,(0x80036000 >> 2) | 0xc7 | (1 << 62)
  sd t1,32(t0)
  sfence.vma
  vle64.v v8,(s0)
  csrr t0,vstart
  bnez t0,fail
  vmv.x.s t0,v8
  li t1,111
  bne t0,t1,fail
  vslidedown.vi v24,v8,2
  vmv.x.s t0,v24
  li t1,99
  bne t0,t1,fail
  li a4,5
  li a7,0
  li t0,0x40003ffc
  vle64.v v8,(t0)
  csrr t0,vstart
  bnez t0,fail
  csrr t0,sstatus
  srli t0,t0,9
  andi t0,t0,3
  li t1,3
  bne t0,t1,fail
  li t0,4
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x56535631
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:j 1b
s_trap:
  csrr t4,scause
  bne t4,a4,fail
  csrr t4,stval
  bne t4,a5,fail
  csrr t4,vstart
  bne t4,a7,fail
  addi s6,s6,1
  beqz a6,skip
  li t4,0x80030ff0
  li t5,111
  sd t5,0(t4)
  li t5,222
  sd t5,8(t4)
  la t4,level0
  li t5,(0x80036000 >> 2) | 0xc7
  sd t5,32(t4)
  sfence.vma
  sret
skip:
  csrr t4,sepc
  addi t4,t4,4
  csrw sepc,t4
  sret
fail:
  lui t0,0x10000
  li t1,1
  sw t1,0x14(t0)
  j 1b
.section .bss,"aw",@nobits
.balign 4096
root:.skip 4096
level1:.skip 4096
level0:.skip 4096

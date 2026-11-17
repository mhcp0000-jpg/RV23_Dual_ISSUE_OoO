.macro check_state length
  csrr t0,vl
  li t1,\length
  bne t0,t1,guest_fail
  csrr t0,vstart
  bnez t0,guest_fail
.endm

.macro check_first vreg,value
  vmv.x.s t0,\vreg
  li t1,\value
  bne t0,t1,guest_fail
.endm

guest_entry:
  # A valid first segment and a fault in field 1 of segment 1.
  li s0,0x400a3ff4
  vsetivli zero,4,e32,m1,tu,mu
  vlseg2e32ff.v v8,(s0)
  check_state 1
  check_first v8,102
  check_first v9,103

  # Two complete segments before a fault in field 0 of segment 2.
  li s0,0x400a3ff0
  vsetivli zero,4,e32,m1,tu,mu
  vlseg2e32ff.v v8,(s0)
  check_state 2
  check_first v8,101
  check_first v9,102
  vslidedown.vi v16,v8,1
  check_first v16,103
  vslidedown.vi v16,v9,1
  check_first v16,104

  # Segment index 0 itself straddles the page boundary. Mask it off and
  # require the first active segment's fault to shorten VL to its index.
  li s0,0x400a3ffc
  vsetivli zero,4,e32,m1,tu,mu
  vmv.v.i v8,7
  vmv.v.i v9,8
  li t0,14
  vmv.s.x v0,t0
  vlseg2e32ff.v v8,(s0),v0.t
  check_state 1
  check_first v8,7
  check_first v9,8

  # Unmask segment 0. The same page boundary now traps on its second
  # field. The handler maps that page and replays the same instruction.
  vsetivli zero,4,e32,m1,tu,mu
first_segment:
  vlseg2e32ff.v v8,(s0)
  check_state 4
  check_first v8,104
  check_first v9,201
  vslidedown.vi v16,v8,1
  check_first v16,202
  vslidedown.vi v16,v9,1
  check_first v16,203
  li a0,0
  ecall
guest_fail:
  li a0,1
  ecall
  unimp

.balign 4
hs_trap:
  csrr t0,scause
  li t1,10
  beq t0,t1,guest_done
  li t1,21
  beqz s5,check_cause
  li t1,13
check_cause:
  bne t0,t1,fail
  bnez s6,fail
  csrr t0,stval
  li t1,0x400a4000
  bne t0,t1,fail
  csrr t0,htval
  li t1,0x200a4000 >> 2
  beqz s5,check_guest_address
  li t1,0
check_guest_address:
  bne t0,t1,fail
  csrr t0,sepc
  la t1,first_segment
  li t2,0x40000000
  sub t1,t1,t2
  bne t0,t1,fail
  csrr t0,vstart
  bnez t0,fail
  csrr t0,vl
  li t1,4
  bne t0,t1,fail
  bnez s5,repair_vs
  la t0,gdata_l0
  li t1,(0x800a4000 >> 2) | 0xdf
  sd t1,1312(t0)
  hfence.gvma
  j replay
repair_vs:
  la t0,vsdata_l0
  li t1,(0x200a4000 >> 2) | 0xcf
  sd t1,1312(t0)
  hfence.vvma
replay:
  addi s6,s6,1
  sret
guest_done:
  bnez a0,fail
  li t0,1
  bne s6,t0,fail
  bnez s5,pass
  # With G-stage repaired, repeat the matrix with the VS-stage leaf absent.
  li s5,1
  li s6,0
  la t0,vsdata_l0
  sd zero,1312(t0)
  hfence.vvma
  la t0,guest_entry
  li t1,0x40000000
  sub t0,t0,t1
  csrw sepc,t0
  sret
pass:
  li t1,1
  j exit
fail:
  li t1,3
exit:
  la t0,tohost
  sd t1,0(t0)
1: j 1b

.section .tohost,"aw"
.balign 8
.globl tohost,fromhost
tohost: .dword 0
fromhost: .dword 0

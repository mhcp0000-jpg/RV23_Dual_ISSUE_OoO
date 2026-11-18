.equ first_pa, 0x80030000
.equ old_pa, 0x80036000
.equ repaired_pa, 0x80038000
.equ next_va, 0x40004000

.macro expect register, value
  li t4,\value
  bne \register,t4,fail
.endm

.macro prepare leaf
  la t0,level0
  li t1,\leaf
  sd t1,32(t0)
  sfence.vma
  sd zero,0(s9)
  li t0,11
  sd t0,0(s1)
  li t0,22
  sd t0,8(s1)
  li t0,33
  sd t0,0(s2)
  li t0,44
  sd t0,8(s2)
  li t0,55
  sd t0,0(s3)
  li t0,66
  sd t0,8(s3)
.endm

.macro expect_pair address, first, second
  ld t0,0(\address)
  ld t1,8(\address)
  expect t0,\first
  expect t1,\second
.endm

s_entry:
  li s0,0x40003000
  li s1,first_pa
  li s2,old_pa
  li s3,repaired_pa
  li s9,0x80037000
  li s8,1
  prepare (old_pa >> 2) | 0x87
  li s7,1
  li a4,13
  li a5,next_va
  li a7,0
  la a3,scalar_read
scalar_read:
  ld t0,0(a5)
  sd s8,0(s9)
  expect t0,55
  expect s6,1

  prepare (old_pa >> 2) | 0x87
  vsetivli zero,4,e64,m2,tu,mu
  la t0,indices
  vl2re64.v v12,(t0)
  vmv.v.i v8,7
  li s7,2
  li a4,13
  li a5,next_va+8
  li a7,2
  la a3,indexed_read
indexed_read:
  vluxei64.v v8,(s0),v12
  sd s8,0(s9)
  expect s6,2
  csrr t0,vstart
  bnez t0,fail
  vmv.x.s t0,v8
  expect t0,22
  vslidedown.vi v16,v8,1
  vmv.x.s t0,v16
  expect t0,11
  vslidedown.vi v16,v8,2
  vmv.x.s t0,v16
  expect t0,66
  vslidedown.vi v16,v8,3
  vmv.x.s t0,v16
  expect t0,55
  expect_pair s1,111,222

  prepare (old_pa >> 2) | 0x47
  li t0,99
  vmv.v.x v8,t0
  li s7,3
  li a4,15
  la a3,indexed_write
indexed_write:
  vsuxei64.v v8,(s0),v12
  sd s8,0(s9)
  expect s6,3
  csrr t0,vstart
  bnez t0,fail
  expect_pair s1,111,222
  expect_pair s2,33,44
  expect_pair s3,99,99

  # The second page remains inaccessible when only the first two indexed
  # lanes are active. The masked load must preserve destination lanes 2–3.
  prepare 0
  li t0,3
  vmv.s.x v0,t0
  vmv.v.i v8,7
  vluxei64.v v8,(s0),v12,v0.t
  vmv.x.s t0,v8
  expect t0,22
  vslidedown.vi v16,v8,1
  vmv.x.s t0,v16
  expect t0,11
  vslidedown.vi v16,v8,2
  vmv.x.s t0,v16
  expect t0,7
  vslidedown.vi v16,v8,3
  vmv.x.s t0,v16
  expect t0,7
  vmv.v.i v8,9
  vsuxei64.v v8,(s0),v12,v0.t
  expect_pair s1,9,9
  expect_pair s2,33,44
  expect_pair s3,55,66
  expect s6,3

  # Elements 0, 1 and 3 write the same word. Element 2 faults on the next
  # page, so the handler must see element 1 and must not see element 3.
  prepare (old_pa >> 2) | 0x47
  la t0,ordered_indices
  vl2re64.v v12,(t0)
  la t0,ordered_values
  vl2re64.v v8,(t0)
  li s7,4
  li a4,15
  li a5,next_va+8
  li a7,2
  la a3,ordered_write
ordered_write:
  vsoxei64.v v8,(s0),v12
  sd s8,0(s9)
  expect s6,4
  csrr t0,vstart
  bnez t0,fail
  expect_pair s1,99,222
  expect_pair s2,33,44
  expect_pair s3,55,77
  vloxei64.v v8,(s0),v12
  vmv.x.s t0,v8
  expect t0,99
  vslidedown.vi v16,v8,1
  vmv.x.s t0,v16
  expect t0,99
  vslidedown.vi v16,v8,2
  vmv.x.s t0,v16
  expect t0,77
  vslidedown.vi v16,v8,3
  vmv.x.s t0,v16
  expect t0,99
  li t1,1
  j finish

s_trap:
  csrr t4,scause
  bne t4,a4,fail
  csrr t4,sepc
  bne t4,a3,fail
  csrr t4,stval
  bne t4,a5,fail
  csrr t4,vstart
  bne t4,a7,fail
  ld t4,0(s9)
  bnez t4,fail
  addi s6,s6,1
  li t4,4
  beq s7,t4,check_ordered_prefix
  li t4,3
  bne s7,t4,repair
  # Both older elements of the indexed store were visible before the fault.
  ld t5,0(s1)
  ld t6,8(s1)
  expect t5,99
  expect t6,99
  j repair
check_ordered_prefix:
  ld t5,0(s1)
  expect t5,22
repair:
  li t5,111
  sd t5,0(s1)
  li t5,222
  sd t5,8(s1)
  la t4,level0
  li t5,(repaired_pa >> 2) | 0xc7
  sd t5,32(t4)
  sfence.vma
  sret

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

.section .rodata
.balign 8
indices: .dword 8,0,0x1008,0x1000
ordered_indices: .dword 0,0,0x1008,0
ordered_values: .dword 11,22,77,99

.section .bss,"aw",@nobits
.balign 4096
root: .space 4096
level1: .space 4096
level0: .space 4096

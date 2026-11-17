.equ FIRST_VA, 0x400a3000
.equ SECOND_VA, 0x400a4000
.equ FIRST_GPA, 0x200a3000
.equ SECOND_GPA, 0x200a4000
.equ PAGE_A, 0x800a9000
.equ PAGE_B, 0x800aa000
.equ PAGE_C, 0x800ab000
.equ VMID, 5
.equ ASID, 9

.macro install_code page,value
  li t0,\page
  li t1,(\value << 20) | 0x513  # addi a0,zero,value
  sw t1,0(t0)
  li t1,0x8067                 # ret
  sw t1,4(t0)
.endm

.macro map_leaves table,first,second,flags
  li t1,(\first >> 2) | \flags
  sd t1,1304(\table)
  li t1,(\second >> 2) | \flags
  sd t1,1312(\table)
.endm

install_ifetch_fixture:
  install_code PAGE_A,41
  install_code PAGE_B,82
  install_code PAGE_C,123
  fence.i
  la t0,gdata_l0
  map_leaves t0,PAGE_A,PAGE_B,0xdf
  # Guest S-mode will edit its own stage-one leaves in the last phase.
  la t0,gvsptes
  la t1,vsdata_l0
  srli t1,t1,2
  ori t1,t1,0xd7
  sd t1,16(t0)
  csrr t0,hgatp
  li t1,VMID << 44
  or t2,t0,t1
  csrw hgatp,t2
  # VMIDLEN=0 means writes to the VMID field are ignored.
  csrr t2,hgatp
  bne t2,t0,fail
  csrr t0,vsatp
  li t1,ASID << 44
  or t0,t0,t1
  csrw vsatp,t0
  csrr t2,vsatp
  bne t2,t0,fail
  hfence.gvma
  hfence.vvma
  j enter_ifetch_guest

.macro fetch_pair first,second
  jalr ra,0(s0)
  li t0,\first
  bne a0,t0,guest_fail
  jalr ra,0(s1)
  li t0,\second
  bne a0,t0,guest_fail
.endm

guest_entry:
  li s0,FIRST_VA
  li s1,SECOND_VA
  fetch_pair 41,82
  ecall                         # HS changes the G-stage mappings.
  fetch_pair 82,123
  ecall                         # HS swaps the VS-stage mappings.
  fetch_pair 123,82
  li t0,0x10002000             # Guest view of its level-0 page table.
  map_leaves t0,FIRST_GPA,SECOND_GPA,0xcf
  li t1,ASID
  sfence.w.inval
  sinval.vma s0,t1
  sinval.vma s1,t1
  sfence.inval.ir
  fetch_pair 82,123
  ecall
guest_fail:
  li s6,-1
  ecall
  unimp

.balign 4
hs_trap:
  csrr t0,scause
  li t1,10
  bne t0,t1,fail
  bltz s6,fail
  beqz s6,change_gstage
  li t0,1
  beq s6,t0,change_vs_stage
  li t0,2
  bne s6,t0,fail
  li t1,1
  j finish
change_gstage:
  la t0,gdata_l0
  map_leaves t0,PAGE_B,PAGE_C,0xdf
  li t1,FIRST_GPA >> 2
  li t2,SECOND_GPA >> 2
  li t3,VMID
  sfence.w.inval
  hinval.gvma t1,t3
  hinval.gvma t2,t3
  sfence.inval.ir
  j advance
change_vs_stage:
  la t0,vsdata_l0
  map_leaves t0,SECOND_GPA,FIRST_GPA,0xcf
  li t1,ASID
  sfence.w.inval
  hinval.vvma s0,t1
  hinval.vvma s1,t1
  sfence.inval.ir
advance:
  addi s6,s6,1
  csrr t0,sepc
  addi t0,t0,4
  csrw sepc,t0
  sret
fail:
  li t1,3
finish:
  la t0,tohost
  sd t1,0(t0)
1: j 1b

.section .tohost,"aw"
.balign 8
.globl tohost,fromhost
tohost: .dword 0
fromhost: .dword 0

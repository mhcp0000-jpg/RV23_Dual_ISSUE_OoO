.equ SHARED_PA, 0x800a3fe0
.equ SHARED_VA, 0x400a3fe0
.equ NEXT_GPA, 0x200a4000
.equ NEXT_PA, 0x800a4000

.macro check_vector_csrs failure
  csrr t0,vl
  bnez t0,\failure
  csrr t0,vtype
  li t1,0x8000000000000000
  bne t0,t1,\failure
.endm

guest_entry:
  li s7,0
  li s0,SHARED_VA
  li t0,-1
  vsetvl zero,zero,t0            # vill=1, vl=0
load_probe:
  vl4re64.v v8,(s0)
  check_vector_csrs guest_fail
  csrr t0,vstart
  bnez t0,guest_fail
  li t0,0x400a3000
  vs4r.v v8,(t0)
  li t1,101
  li t2,109
check_restore:
  ld t3,0(t0)
  bne t3,t1,guest_fail
  addi t0,t0,8
  addi t1,t1,1
  bne t1,t2,check_restore

  li a0,1
  ecall                         # Zero backing data and re-arm translation fault.
  li s7,1
store_probe:
  vs4r.v v8,(s0)
  check_vector_csrs guest_fail
  csrr t0,vstart
  bnez t0,guest_fail
  mv t0,s0
  li t1,99
  li t2,SHARED_VA + 32
check_unrepeated:
  ld t3,0(t0)
  bne t3,t1,guest_fail
  addi t0,t0,8
  bne t0,t2,check_unrepeated
  li t1,105
  li t2,109
check_saved:
  ld t3,0(t0)
  bne t3,t1,guest_fail
  addi t0,t0,8
  addi t1,t1,1
  bne t1,t2,check_saved
  li a0,0
  ecall
guest_fail:
  li a0,-1
  ecall
  unimp

.balign 4
hs_trap:
  csrr t0,scause
  li t1,10
  beq t0,t1,guest_call
  li t1,21
  beqz s5,check_access
  li t1,13
check_access:
  slli t2,s7,1
  add t1,t1,t2                 # load cause + 2 gives store cause.
  bne t0,t1,fail
  bne s6,s7,fail               # One fault per probe.
  csrr t0,stval
  li t1,SHARED_VA + 32
  bne t0,t1,fail
  csrr t0,htval
  li t1,NEXT_GPA >> 2
  beqz s5,check_gpa
  li t1,0
check_gpa:
  bne t0,t1,fail
  la t0,load_probe
  beqz s7,check_pc
  la t0,store_probe
check_pc:
  li t1,0x40000000
  sub t0,t0,t1
  csrr t2,sepc
  bne t0,t2,fail
  check_vector_csrs fail
  csrr t0,vstart
  li t1,4                      # Whole load EEW=64, four elements transferred.
  beqz s7,check_start
  li t1,32                     # Whole store EEW=8, 32 elements transferred.
check_start:
  bne t0,t1,fail
  li t0,SHARED_PA
  li t1,101
  li t2,105
  li t4,0
  beqz s7,replace_prefix
  li t4,99
replace_prefix:
  ld t3,0(t0)
  bne t3,t1,fail
  sd t4,0(t0)                  # Detect any replay of completed elements.
  addi t0,t0,8
  addi t1,t1,1
  bne t1,t2,replace_prefix
  beqz s7,repair_pte
  li t2,SHARED_PA + 64
check_unwritten:
  ld t3,0(t0)
  bnez t3,fail
  addi t0,t0,8
  bne t0,t2,check_unwritten
repair_pte:
  bnez s5,repair_vs
  la t0,gdata_l0
  li t1,(NEXT_PA >> 2) | 0xdf
  sd t1,1312(t0)
  hfence.gvma
  j replay
repair_vs:
  la t0,vsdata_l0
  li t1,(NEXT_GPA >> 2) | 0xcf
  sd t1,1312(t0)
  hfence.vvma
replay:
  addi s6,s6,1
  sret

guest_call:
  beqz a0,case_done
  li t0,1
  bne a0,t0,fail
  bne s6,t0,fail
  li t0,SHARED_PA
  li t1,SHARED_PA + 64
clear_memory:
  sd zero,0(t0)
  addi t0,t0,8
  bne t0,t1,clear_memory
  bnez s5,arm_vs_store
  la t0,gdata_l0
  sd zero,1312(t0)
  hfence.gvma
  j advance
arm_vs_store:
  la t0,vsdata_l0
  sd zero,1312(t0)
  hfence.vvma
advance:
  csrr t0,sepc
  addi t0,t0,4
  csrw sepc,t0
  sret

case_done:
  li t0,2
  bne s6,t0,fail
  bnez s5,pass
  li s5,1
  li s6,0
  li t0,SHARED_PA
  li t1,101
  li t2,109
reset_data:
  sd t1,0(t0)
  addi t0,t0,8
  addi t1,t1,1
  bne t1,t2,reset_data
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

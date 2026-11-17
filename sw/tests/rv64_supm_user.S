.section .text.init,"ax"
.option norvc
.option norelax
.globl _start

.equ DATA_PA, 0x80060000
.equ USER_ALIAS, 0x40000000
.equ TAG, 0xfe00000000000000
.equ INITIAL, 0x0123456789abcdef
.equ UPDATED, 0x76543210fedcba98
.equ PMM7, 0x200000000

_start:
    lui t0,0x02000
    sw zero,0(t0)
    li t0,-1
    csrw pmpaddr0,t0
    li t0,31
    csrw pmpcfg0,t0
    la t0,m_trap
    csrw mtvec,t0
    la t0,hs_trap
    csrw stvec,t0
    # U ECALL and U load/store access/page faults go to HS. HS ECALL goes to M.
    li t0,0xa1a0
    csrw medeleg,t0
    csrr t1,medeleg
    bne t0,t1,fail
    la t0,root
    li t1,0x200000df       # User RWX alias at VA 0x40000000.
    sd t1,8(t0)
    li t1,0x200000cf       # Supervisor RWX identity map at VA 0x80000000.
    sd t1,16(t0)
    li s5,0

launch:
    li s0,DATA_PA
    li t0,INITIAL
    sd t0,0(s0)
    la t1,user_entry
    la s6,user_select
    la s7,user_load
    la s8,user_store
    la s9,user_done
    li s10,5               # Bare load access fault.
    li s11,7               # Bare store access fault.
    beqz s5,enter_user
    la t0,root
    srli t0,t0,12
    li t2,0x8000000000000000
    or t0,t0,t2
    csrw satp,t0
    sfence.vma
    li t2,USER_ALIAS
    sub t1,t1,t2
    sub s0,s0,t2
    sub s6,s6,t2
    sub s7,s7,t2
    sub s8,s8,t2
    sub s9,s9,t2
    li s10,13              # Sv39 load page fault.
    li s11,15              # Sv39 store page fault.
enter_user:
    csrw mstatus,zero
    csrw mepc,t1
    mret

user_entry:
    li t0,TAG
    or s1,s0,t0
    li s2,0
    li s3,0
    li s4,0
user_iteration:
    # Request 0, then 7, then 0 again via the supervisor service.
    mv a0,s2
user_select:
    ecall
    bne a0,s2,user_fail
    ld t1,0(s0)
    li t2,INITIAL
    bne t1,t2,user_fail
    lbu t1,0(s0)
    li t2,0xef
    bne t1,t2,user_fail
    li t1,-1
user_load:
    ld t1,0(s1)
    li t2,-1
    beqz s2,check_load
    li t2,INITIAL
check_load:
    bne t1,t2,user_fail
    li t0,UPDATED
user_store:
    sd t0,0(s1)
    ld t1,0(s0)
    li t2,INITIAL
    beqz s2,check_store
    li t2,UPDATED
check_store:
    bne t1,t2,user_fail
    li t0,INITIAL
    sd t0,0(s0)
    addi s3,s3,1
    li t0,3
    beq s3,t0,user_done
    xori s2,s2,7
    j user_iteration
user_done:
    ecall
user_fail:
    unimp

.balign 4
hs_trap:
    csrr t3,sstatus
    andi t3,t3,0x100
    bnez t3,hs_fail
    csrr t3,scause
    csrr t4,sepc
    csrr t5,stval
    li t6,8
    beq t3,t6,user_request
    bnez s2,hs_fail
    bne t5,s1,hs_fail
    bne t3,s10,check_store_fault
    bne t4,s7,hs_fail
    j fault_done
check_store_fault:
    bne t3,s11,hs_fail
    bne t4,s8,hs_fail
fault_done:
    addi s4,s4,1
    j resume_user
user_request:
    bnez t5,hs_fail
    beq t4,s9,hs_done
    bne t4,s6,hs_fail
    li t5,7
    beq a0,t5,enable_mask
    bnez a0,hs_fail
    li t5,0
    j apply_mask
enable_mask:
    li t5,PMM7
apply_mask:
    csrw senvcfg,t5
    csrr t6,senvcfg
    bne t6,t5,hs_fail
resume_user:
    addi t4,t4,4
    csrw sepc,t4
    sret
hs_done:
    li t0,3
    bne s3,t0,hs_fail
    li t0,4
    bne s4,t0,hs_fail
hs_finish_ecall:
    ecall
hs_fail:
    li s5,-1
    ecall
    j hs_fail

.balign 4
m_trap:
    bltz s5,fail
    csrr t0,mcause
    li t1,9
    bne t0,t1,fail
    csrr t0,mtval
    bnez t0,fail
    csrr t0,mepc
    la t1,hs_finish_ecall
    bne t0,t1,fail
    csrr t0,mstatus
    srli t0,t0,11
    andi t0,t0,3
    li t1,1
    bne t0,t1,fail
    bnez s5,pass
    li s5,1
    j launch
pass:
    li t1,1
    j exit
fail:
    li t1,3
exit:
    la t0,tohost
    sd t1,0(t0)
stop:
    j stop

.section .tohost,"aw"
.balign 8
.globl tohost,fromhost
tohost:
    .dword 0
fromhost:
    .dword 0

.section .bss,"aw",@nobits
.balign 4096
root:
    .space 4096

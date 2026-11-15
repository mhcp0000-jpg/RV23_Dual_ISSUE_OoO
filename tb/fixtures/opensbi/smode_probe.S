/* SPDX-License-Identifier: BSD-2-Clause */
    .section .text
    .option norvc
    .globl _start
_start:
    li s0, 1
    bnez a0, fail
    li t0, 0x80090000
    bne a1, t0, fail
    lwu t0, 0(a1)
    li t1, 0xedfe0dd0
    bne t0, t1, fail
    csrr t0, satp
    bnez t0, fail

    li s0, 2
    li a7, 0x10              /* SBI BASE */
    li a6, 0                 /* Get spec version */
    ecall
    bnez a0, fail
    beqz a1, fail

    li s0, 3
    lla t0, supervisor_trap
    csrw stvec, t0
    rdtime a0
    li t0, 5000
    add a0, a0, t0
    li a7, 0x54494d45        /* SBI TIME */
    li a6, 0                 /* Set timer */
    ecall
    bnez a0, fail
    li t0, 1 << 5
    csrs sie, t0
    csrsi sstatus, 2
1:  wfi
    j 1b

    .balign 4
supervisor_trap:
    li s0, 4
    csrr t0, scause
    li t1, 0x8000000000000005
    bne t0, t1, fail
    lla t0, success
    li t1, 0x10000000
2:  lbu t2, 0(t0)
    beqz t2, 3f
    sw t2, 24(t1)
    addi t0, t0, 1
    j 2b
3:  sw zero, 20(t1)
    j 3b

fail:
    li t0, 0x10000000
    sw s0, 20(t0)
    j fail

success:
    .asciz "OPENSBI S-MODE DTB AND TIMER PASS\n"

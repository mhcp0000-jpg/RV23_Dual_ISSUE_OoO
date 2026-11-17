/* SPDX-License-Identifier: BSD-2-Clause */
    .section .text
    .option norelax
    .globl _start
_start:
#ifdef RV23_LINUX_VECTOR
    /* Skip argc, argv and envp to inspect AT_HWCAP in the ELF aux vector. */
    ld t0,0(sp)
    slli t0,t0,3
    add t0,t0,sp
    addi t0,t0,16
skip_env:
    ld t1,0(t0)
    addi t0,t0,8
    bnez t1,skip_env
find_hwcap:
    ld t1,0(t0)
    beqz t1,fail
    li t2,16                 /* AT_HWCAP */
    beq t1,t2,check_hwcap
    addi t0,t0,16
    j find_hwcap
check_hwcap:
    ld t1,8(t0)
    li t2,1 << ('v' - 'a')
    and t1,t1,t2
    beqz t1,fail

    /* The first vector instruction exercises Linux lazy state enable. */
    vsetivli t0,4,e32,m1,ta,ma
    li t1,4
    bne t0,t1,fail
    vid.v v8
    li t0,17
    vadd.vx v8,v8,t0
    lla t0,vector_result
    vse32.v v8,(t0)
    li t1,17
    li t2,21
check_vector:
    lw t3,0(t0)
    bne t3,t1,fail
    addi t0,t0,4
    addi t1,t1,1
    bne t1,t2,check_vector
#endif
    li a0, -100              /* AT_FDCWD */
    lla a1, console
    li a2, 1                 /* O_WRONLY */
    li a7, 56                /* openat */
    ecall
    bltz a0, fail

    lla a1, marker
    lla s0, marker_end
    sub s0, s0, a1
    mv a2, s0
    li a7, 64                /* write */
    ecall
    bne a0, s0, fail

    li a0, 0xfee1dead         /* LINUX_REBOOT_MAGIC1 */
    li a1, 672274793          /* LINUX_REBOOT_MAGIC2 */
    li a2, 0x4321fedc         /* LINUX_REBOOT_CMD_POWER_OFF */
    li a3, 0
    li a7, 142               /* reboot */
    ecall

fail:
    li a0, 1
    li a7, 93                /* exit */
    ecall
1:  j 1b

    .section .rodata
console:
    .asciz "/dev/kmsg"
marker:
#ifdef RV23_LINUX_VECTOR
    .ascii "<0>RV23 LINUX USER VECTOR PASS\n"
#endif
    .ascii "<0>RV23 LINUX INIT PASS\n"
marker_end:
#ifdef RV23_LINUX_VECTOR
    .section .bss
    .balign 16
vector_result:
    .space 16
#endif

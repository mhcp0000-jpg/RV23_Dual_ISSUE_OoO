/* SPDX-License-Identifier: BSD-2-Clause */
    .section .text
    .option norelax
    .globl _start
_start:
    /* Linux RISC-V prctl options and PMLEN field from uapi/linux/prctl.h. */
    li a0,56                 /* PR_GET_TAGGED_ADDR_CTRL */
    jal ra,supm_prctl
    bnez a0,supm_fail
    li s2,(7 << 24) | 1      /* PMLEN=7 and PR_TAGGED_ADDR_ENABLE */
    li a0,55                 /* PR_SET_TAGGED_ADDR_CTRL */
    mv a1,s2
    jal ra,supm_prctl_args
    bnez a0,supm_fail
    li a0,56
    jal ra,supm_prctl
    bne a0,s2,supm_fail

    lla s3,supm_words
    li t0,0x5a00000000000000
    or s4,s3,t0
    li t0,19
    sd t0,0(s4)
    ld t1,0(s3)
    bne t0,t1,supm_fail
    ld t1,0(s4)
    bne t0,t1,supm_fail
    li t0,23
    sd t0,8(s3)
    vsetivli zero,2,e64,m1,tu,mu
    vle64.v v8,(s4)
    vadd.vi v8,v8,5
    vse64.v v8,(s4)
    ld t0,0(s3)
    li t1,24
    bne t0,t1,supm_fail
    ld t0,8(s3)
    li t1,28
    bne t0,t1,supm_fail

    li a0,55
    jal ra,supm_prctl
    bnez a0,supm_fail
    li a0,56
    jal ra,supm_prctl
    bnez a0,supm_fail
    ld t0,0(s3)
    li t1,24
    bne t0,t1,supm_fail

    li a0,-100
    lla a1,supm_console
    li a2,1
    li a7,56
    ecall
    bltz a0,supm_fail
    lla a1,supm_marker
    lla s2,supm_marker_end
    sub s2,s2,a1
    mv a2,s2
    li a7,64
    ecall
    bne a0,s2,supm_fail
    j vector_init_start

supm_prctl:
    li a1,0
supm_prctl_args:
    li a2,0
    li a3,0
    li a4,0
    li a7,167
    ecall
    ret

supm_fail:
    li a0,1
    li a7,93
    ecall
1:  j 1b

    .section .rodata
supm_console:
    .asciz "/dev/kmsg"
supm_marker:
    .ascii "<0>RV23 LINUX USER SUPM PASS\n"
supm_marker_end:

    .section .bss
    .balign 16
supm_words:
    .space 16

#define _start vector_init_start
#define RV23_LINUX_VECTOR 1
#include "linux_init.S"

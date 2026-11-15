/* SPDX-License-Identifier: BSD-2-Clause */
    .section .text
    .option norelax
    .globl _start
_start:
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
    .ascii "<0>RV23 LINUX INIT PASS\n"
marker_end:

# rvmodel_macros.h
# DUT-specific macro definitions for Sail reference model
# Jordan Carlin jcarlin@hmc.edu October 2025, Sadhvi Narayana sanarayanan@hmc.edu February 2026
# SPDX-License-Identifier: BSD-3-Clause

#ifndef _RVMODEL_MACROS_H
#define _RVMODEL_MACROS_H

#define CLINT_BASE_ADDRESS 0x02000000

#define RVMODEL_DATA_SECTION \
        .pushsection .tohost,"aw",@progbits;                \
        .balign 8; .global tohost; tohost: .dword 0;         \
        .balign 8; .global fromhost; fromhost: .dword 0;     \
        .popsection

#define STANDARD_SM_SUPPORTED

##### STARTUP #####

# Perform boot operations. Can be empty or left undefined unless needed for
# DUT-specific behavior such as turning on a memory controller or
# initializing custom state.
// #define RVMODEL_BOOT

// Custom RVMODEL_BOOT_TO_MMODE overrides default RVTEST_BOOT_TO_MMODE
// if defined.  For most DUTs, the default should work and this macro
// should not be defined.  If no M-mode or CSRs are implemented, define this
// macro as blank to bypass the boot process.  If a nonconforming
// M-mode is implemented, define this macro to set up the necessary
// state in a fashion similar to RVTEST_BOOT_TO_MMODE.
//#define RVMODEL_BOOT_TO_MMODE

##### TERMINATION #####

// SAIL uses HTIF (Host-Target Interface) to terminate simulation.
// Writing to 'tohost' with value 1 indicates success, 3 indicates failure.

# Terminate test with a pass indication.
# When the test is run in simulation, this should end the simulation.
#define RVMODEL_HALT_PASS \
  li t0,0x10000000; \
  sw zero,0x14(t0); \
  1:j 1b;



# Terminate test with a fail indication.
# When the test is run in simulation, this should end the simulation.
#define RVMODEL_HALT_FAIL \
  li t0,0x10000000; \
  li t1,1; \
  sw t1,0x14(t0); \
  1:j 1b;



##### IO #####

# Initialization steps needed prior to writing to the console
# _R1, _R2, and _R3 can be used as temporary registers if needed.
# Do not modify any other registers (or make sure to restore them).
# Can be empty or left undefined if no initialization is needed.
// #define RVMODEL_IO_INIT(_R1, _R2, _R3)


# Prints a null-terminated string using a DUT specific mechanism.
# A pointer to the string is passed in _STR_PTR.
# _R1, _R2, and _R3 can be used as temporary registers if needed.
# Do not modify any other registers (or make sure to restore them).
#define RVMODEL_IO_WRITE_STR(_R1, _R2, _R3, _STR_PTR) \
  li _R2,0x10000018; \
  1:lbu _R1,0(_STR_PTR); \
  beqz _R1,2f; \
  sw _R1,0(_R2); \
  addi _STR_PTR,_STR_PTR,1; \
  j 1b; \
  2:


##### Access Fault #####

#define RVMODEL_ACCESS_FAULT_ADDRESS 0x00000000

##### Machine Timer #####

#define RVMODEL_MTIMECMP_ADDRESS  0x02004000  /* Address of mtimecmp CSR */

#define RVMODEL_MTIME_ADDRESS  0x0200BFF8  /* Address of mtime CSR */

##### Machine Interrupts #####
#define RVMODEL_MAX_CYCLES_PER_TIMER_TICK 1

// Interrupt latency configuration
#define RVMODEL_INTERRUPT_LATENCY 128

#define RVMODEL_TIMER_INT_SOON_DELAY 100

#define SIG_ADDRESS  (0xC000000 + 0x4)  /* Address of memory mapped simple interrupt generator */
#define RVMODEL_SET_MEXT_INT(_R1, _R2) \
  li _R2,0x0c000004; \
  li _R1,1; \
  sw _R1,0(_R2); \
  li _R2,0x0c002000; \
  li _R1,2; \
  sw _R1,0(_R2); \
  li _R2,0x0c200000; \
  sw zero,0(_R2); \
  li _R2,0x10000008; \
  li _R1,0x101; \
  sw _R1,0(_R2);



#define RVMODEL_CLR_MEXT_INT(_R1, _R2) \
  li _R2,0x10000008; \
  li _R1,1; \
  sw _R1,0(_R2); \
  li _R2,0x0c200004; \
  lw _R1,0(_R2); \
  sw _R1,0(_R2);


#define RVMODEL_MSIP_ADDRESS (CLINT_BASE_ADDRESS + 0x0)
#define RVMODEL_SET_MSW_INT(_R1, _R2)        \
  li _R1, 1;                 \
  li _R2, RVMODEL_MSIP_ADDRESS;              \
  sw _R1, 0(_R2);


#define RVMODEL_CLR_MSW_INT(_R1, _R2)        \
  li _R2, RVMODEL_MSIP_ADDRESS;              \
  sw zero, 0(_R2);



##### Supervisor Interrupts #####

#define RVMODEL_SET_SEXT_INT(_R1, _R2) \
  li _R1,512; \
  csrs mip,_R1;


#define RVMODEL_CLR_SEXT_INT(_R1, _R2) \
  li _R1,512; \
  csrc mip,_R1;



#define RVMODEL_SET_SSW_INT(_R1, _R2) \
  li _R1,2; \
  csrs mip,_R1;


#define RVMODEL_CLR_SSW_INT(_R1, _R2) \
  li _R1,2; \
  csrc mip,_R1;


#endif // _RVMODEL_MACROS_H

.section .text.init,"ax"
.option norvc
.globl _start
_start:
  lui t0,0x02000
  sw zero,0(t0)
  la t0,m_trap
  csrw mtvec,t0
  li t0,-1
  csrw pmpaddr0,t0
  li t0,15
  csrw pmpcfg0,t0
  li t0,0x200000000
  csrw senvcfg,t0
  csrr t1,senvcfg
  bne t0,t1,fail
  li s6,0
  li s0,DATA_ADDRESS
  li s1,DATA_ADDRESS | 0xfe00000000000000
  li t0,0x80070000
  li t1,0x12345678
  sd t1,0(t0)
#if VIRTUAL
  la t1,root
  li t0,0x200000df
  sd t0,16(t1)                 # U executable identity SRAM/code
  li t0,0xd7
  sd t0,0(t1)                  # U accessible MMIO
  la t0,level1
  srli t0,t0,2
  ori t0,t0,1
  sd t0,8(t1)
  la t1,level1
  la t0,level0
  srli t0,t0,2
  ori t0,t0,1
  sd t0,0(t1)
  la t1,level0
  li t0,(0x80070000 >> 2) | 0xd7
  sd t0,24(t1)
  la t0,root
  srli t0,t0,12
  li t1,8
  slli t1,t1,60
  or t0,t0,t1
  csrw satp,t0
  sfence.vma
#endif
  # MPRV selects the U-mode pointer-mask setting as well as its PMP/translation.
  li t0,0x20000
  csrw mstatus,t0
  ld t1,0(s1)
  li t2,0x12345678
  bne t1,t2,fail
  csrw mstatus,zero
  la t0,u_entry
  csrw mepc,t0
  li t0,0x86000                # MXR=1, FS=Dirty, MPP=U
  csrw mstatus,t0
  mret
u_entry:
  li a4,FAULT_CAUSE
  mv a5,s1
mxr_load:
  ld t1,0(s1)                 # MXR disables pointer masking; handler retries
  li t2,0x12345678
  bne t1,t2,fail
  li t1,0x88776655
  sd t1,0(s1)
  ld t2,0(s0)
  bne t1,t2,fail
  li t1,3
  amoadd.d t2,t1,(s1)
  li t3,0x88776655
  bne t2,t3,fail
  lr.d t2,(s1)
  addi t2,t2,1
  sc.d t3,t2,(s1)
  bnez t3,fail
  ld t3,0(s0)
  bne t2,t3,fail
  li t1,0x3f800000
  sw t1,0(s1)
  flw ft0,0(s1)
  fsw ft0,4(s1)
  lw t2,4(s0)
  bne t1,t2,fail
  # Ordinary misalignment now succeeds through the main-memory assist.
  ld t1,1(s1)
  sd t1,9(s1)
  ld t2,9(s1)
  bne t1,t2,fail
  # LR/SC still require alignment; mtval contains the transformed address.
  li a4,4
  addi a5,s0,1
  addi t0,s1,1
  lr.d t1,(t0)
  li a4,6
  sc.d t2,t1,(t0)
  # Bit 56 is outside PMLEN=7 and must still participate in address validity.
  li t0,DATA_ADDRESS | 0xab00000000000000
  li a4,FAULT_CAUSE
  li a5,TRANSFORMED_BAD_ADDRESS
  ld t1,0(t0)
  # Fetch is implicit: a tagged JALR target must not be masked.
  li a4,FETCH_FAULT_CAUSE
  li a5,0xfe00000080000000
  jalr zero,0(a5)
fetch_resume:
  li t0,5
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x504d4d37
  sw t1,0xc(t0)
  sw zero,0x14(t0)
1:j 1b
m_trap:
  csrr t4,mcause
  bne t4,a4,fail
  csrr t4,mtval
  bne t4,a5,fail
  addi s6,s6,1
  li t4,1
  beq s6,t4,disable_mxr
  li t4,5
  beq s6,t4,resume_fetch
  csrr t4,mepc
  addi t4,t4,4
  csrw mepc,t4
  mret
disable_mxr:
  li t4,0x80000
  csrc mstatus,t4
  mret
resume_fetch:
  la t4,fetch_resume
  csrw mepc,t4
  mret
fail:
  lui t0,0x10000
  li t1,1
  sw t1,0x14(t0)
  j 1b
.section .bss,"aw",@nobits
.balign 4096
root:.space 4096
level1:.space 4096
level0:.space 4096

.section .text.init,"ax"
.option norvc
.globl _start
_start:
  lui t0,0x02000
  sw zero,0(t0)
  la t0,fail
  csrw mtvec,t0
  li t0,-1
  csrw pmpaddr0,t0
  li t0,31
  csrw pmpcfg0,t0
  la t0,hs_trap
  csrw stvec,t0
  li t0,0xf0b7ff
  csrw medeleg,t0
  la t1,vsroot
  la t0,vslevel1
  srli t0,t0,2
  ori t0,t0,1
  sd t0,8(t1)
  la t1,vslevel1
  li t0,(0x80000000 >> 2) | 0xdf
  sd t0,0(t1)                 # VU mappings require U=1
  la t0,vsroot
  srli t0,t0,12
  li t1,0x8000000000000000
  or t0,t0,t1
  csrw vsatp,t0
  li t0,0x800a0000
  li t1,11
  sd t1,0(t0)
  li t1,0x11223344
  sd t1,8(t0)
  # M-mode ordinary memory uses VS/G stages under MPRV+MPV.
  li s7,1
  li s6,0
  li t0,0x40000
  csrw vsstatus,t0            # SUM enables VS access to the U page
  li s0,0x400a0000
  li t0,0x8000020800          # MPV=1, MPRV=1, MPP=S
  csrw mstatus,t0
  ld t1,0(s0)
  li t2,11
  bne t1,t2,fail
  li t1,22
  sd t1,0(s0)
  csrw mstatus,zero
  li t0,0x800a0000
  ld t1,0(t0)
  li t2,22
  bne t1,t2,fail
  la t0,hs_entry
  csrw mepc,t0
  li t0,0x800
  csrw mstatus,t0
  mret
hs_entry:
  li s7,2
  li t0,0x2000000000200      # HU=1, SPVP=0, HUPMM=7-bit masking
  csrw hstatus,t0
  la t0,u_entry
  csrw sepc,t0
  csrw sstatus,zero
  sret
u_entry:
  li s7,3
  li s0,0xfe000000400a0000
  hlv.d t0,(s0)              # HUPMM applies only to actual U HLV/HSV
  li t1,22
  bne t0,t1,fail
  li t0,33
  hsv.d t0,(s0)
  li t0,0x800a0000
  ld t1,0(t0)
  li t2,33
  bne t1,t2,fail
  li t0,0x400a0008
  hlvx.wu t1,(t0)
  li t2,0x11223344
  bne t1,t2,fail
  li s7,4
  hlvx.wu t1,(s0)            # HLVX ignores HUPMM: noncanonical VS VA -> 13
  li s7,5
  hfence.vvma                # HU does not permit fences in U -> 2
  li s7,6
  li s0,0x400a0000
  hlv.d t0,(s0)              # HS clears HU after the fence trap -> 2
  li a0,1
  ecall
1:j 1b
hs_trap:
  csrr t0,hstatus
  andi t0,t0,0x80
  bnez t0,fail               # actual U, never virtualized
  csrr t0,scause
  addi s6,s6,1
  li t1,8
  beq t0,t1,finish
  li t1,4
  beq s7,t1,hlvx_fault
  li t1,2
  bne t0,t1,fail
  li t0,0x200
  csrc hstatus,t0
resume:
  csrr t0,sepc
  addi t0,t0,4
  csrw sepc,t0
  sret
hlvx_fault:
  li t1,13
  bne t0,t1,fail
  csrr t0,stval
  li t1,0xfe000000400a0000
  bne t0,t1,fail
  j resume
finish:
  li t0,1
  bne a0,t0,fail
  li t0,4
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x48595034
  sw t1,0xc(t0)
  sw zero,0x14(t0)
  j 1b
fail:
  lui t0,0x10000
  sw s7,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j 1b
.section .bss,"aw",@nobits
.balign 4096
vsroot:.skip 4096
vslevel1:.skip 4096

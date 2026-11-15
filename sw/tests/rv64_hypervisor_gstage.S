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
  li t0,7
  csrw mcounteren,t0
  csrw scounteren,t0
  li t0,0xc0000000000000f0
  csrw menvcfg,t0
  li t0,0xf0b7ff
  csrw medeleg,t0
  la t0,hs_trap
  csrw stvec,t0
  la t1,vsroot
  li t0,0xcf
  sd t0,0(t1)                  # guest I/O identity superpage
  li t0,(0x10001000 >> 2) | 1
  sd t0,8(t1)
  la t1,vslevel1
  li t0,(0x20000000 >> 2) | 0xcf
  sd t0,0(t1)                  # guest 0x40000000 -> SRAM 0x80000000
  # G-stage translates the VS tables and final guest physical accesses.
  la t1,groot
  la t0,glevel1
  srli t0,t0,2
  ori t0,t0,1
  sd t0,0(t1)
  la t1,glevel1
  la t0,gvsptes
  srli t0,t0,2
  ori t0,t0,1
  sd t0,1024(t1)             # GPA 0x10000000: VS page-table pages
  li t0,(0x80000000 >> 2) | 0xdf
  li t2,2048
  add t1,t1,t2
  sd t0,0(t1)                # GPA 0x20000000 -> physical SRAM, U/R/W/X/A/D
  la t1,gvsptes
  la t0,vsroot
  srli t0,t0,2
  ori t0,t0,0x53
  sd t0,0(t1)
  la t0,vslevel1
  srli t0,t0,2
  ori t0,t0,0x53
  sd t0,8(t1)
  la t0,groot
  srli t0,t0,12
  li t1,0x8000000000000000
  or t0,t0,t1
  csrw hgatp,t0
  li t0,0x10000
  li t1,0x8000000000000000
  or t0,t0,t1
  csrw vsatp,t0
  li t0,0x2200
  csrw vsstatus,t0
  li t0,0x800a0000
  li t1,11
  sd t1,0(t0)
  li t1,0x3ff0000000000000
  sd t1,8(t0)
  la t0,hs_entry
  csrw mepc,t0
  li t0,0x2a00
  csrw mstatus,t0
  li s6,0
  li s7,0
  mret
hs_entry:
  li s7,1
  li t0,0x100                 # HLV/HSV use VS privilege (SPVP=1)
  csrw hstatus,t0
  li t0,7
  csrw hcounteren,t0
  li t0,0xc000000000000000
  csrw hstateen0,t0
  li t0,0xc0000000000000f0
  csrw henvcfg,t0
  li s0,0x400a0000
  hlv.d t1,(s0)
  li t2,11
  bne t1,t2,fail
  li t1,22
  hsv.d t1,(s0)
  li t0,0x800a0000
  ld t1,0(t0)
  li t2,22
  bne t1,t2,fail
  hfence.vvma
  hfence.gvma
  hinval.vvma zero,zero
  hinval.gvma zero,zero
  la t0,guest_entry
  li t1,0x40000000
  sub t0,t0,t1
  csrw sepc,t0
  li t0,0x180                 # SPV=1 and SPVP=1; HS SRET enters VS
  csrw hstatus,t0
  li t0,0x2300                # HS FS/VS=Initial, SPP=1
  csrw sstatus,t0
  sret
guest_entry:
  li s7,2
  li s0,0x400a0000
  ld t0,0(s0)
  li t1,22
  bne t0,t1,guest_fail
  li t0,33
  sd t0,0(s0)
  li t0,5
  amoadd.d t1,t0,(s0)
  li t2,33
  bne t1,t2,guest_fail
  lr.d t1,(s0)
  addi t1,t1,2
  sc.d t2,t1,(s0)
  bnez t2,guest_fail
  ld t1,0(s0)
  li t2,40
  bne t1,t2,guest_fail
  fld ft0,8(s0)
  fadd.d ft1,ft0,ft0
  fsd ft1,16(s0)
  ld t1,16(s0)
  li t2,0x4000000000000000
  bne t1,t2,guest_fail
  vsetivli t0,4,e32,m1,tu,mu
  li t1,4
  bne t0,t1,guest_fail
  vmv.v.i v1,3
  vadd.vi v2,v1,4
  addi s1,s0,128
  vse32.v v2,(s1)
  vmv.v.i v8,0
  vle32.v v8,(s1)
  vmv.x.s t0,v8
  li t1,7
  bne t0,t1,guest_fail
  lw t0,0(s1)
  bne t0,t1,guest_fail
  li s7,3
  addi s1,s0,256
  li t0,-1
  sd t0,0(s1)
  sd t0,56(s1)
  cbo.zero 0(s1)
  ld t0,0(s1)
  bnez t0,guest_fail
  ld t0,56(s1)
  bnez t0,guest_fail
  cbo.clean 0(s1)
  cbo.flush 0(s1)
  cbo.inval 0(s1)
  sfence.vma
  li a0,0
  ecall
  li s7,5
store_fault:
  sd zero,24(s0)             # G-stage W denied by HS after the first ECALL
  li s7,4
  csrr t2,hstatus             # HS-qualified CSR -> virtual instruction
  hfence.vvma                 # H instruction in VS -> virtual instruction
  vmv.x.s t0,v8
  li t1,7
  bne t0,t1,guest_fail
  csrr t0,cycle
  csrr t0,time
  li a0,1
  ecall
guest_fail:
  li a0,255
  ecall
1:j 1b
hs_trap:
  csrr t0,hstatus
  andi t0,t0,0x180
  li t1,0x180
  bne t0,t1,fail
  csrr t0,scause
  addi s6,s6,1
  li t1,23
  beq t0,t1,guest_store_fault
  li t1,20
  beq t0,t1,implicit_fetch_fault
  li t1,22
  beq t0,t1,virtual_instruction
  li t1,10
  bne t0,t1,fail
  li t0,255
  beq a0,t0,fail
  bnez a0,finish
  li t0,0x800a0000
  ld t1,0(t0)
  li t2,40
  bne t1,t2,fail
  csrr t0,sstatus
  li t1,0x6600
  and t0,t0,t1
  bne t0,t1,fail
  csrr t0,vsstatus
  and t0,t0,t1
  bne t0,t1,fail
  la t0,glevel1
  li t1,(0x80000000 >> 2) | 0xdb
  li t2,2048
  add t0,t0,t2
  sd t1,0(t0)
  hfence.gvma
resume:
  csrr t0,sepc
  addi t0,t0,4
  csrw sepc,t0
  sret
virtual_instruction:
  csrr t0,sepc
  hlvx.wu t1,(t0)
  csrr t2,stval
  bne t1,t2,fail
  j resume
guest_store_fault:
  li t0,5
  bne s7,t0,fail
  csrr t0,stval
  li t1,0x400a0018
  bne t0,t1,fail
  csrr t0,htval
  li t1,(0x200a0018 >> 2)
  bne t0,t1,fail
  csrr t0,htinst
  bnez t0,fail
  csrr t0,hstatus
  andi t0,t0,0x40
  beqz t0,fail
  la t0,glevel1
  li t1,(0x80000000 >> 2) | 0xdf
  li t2,2048
  add t0,t0,t2
  sd t1,0(t0)
  la t0,gvsptes
  sd zero,0(t0)              # deny G access to the VS root page
  hfence.gvma
  hfence.vvma
  j resume
implicit_fetch_fault:
  li t0,5
  bne s7,t0,fail
  csrr t0,htval
  li t1,(0x10000008 >> 2)
  bne t0,t1,fail
  csrr t0,htinst
  li t1,0x3000
  bne t0,t1,fail
  csrr t0,stval
  csrr t1,sepc
  bne t0,t1,fail
  la t1,gvsptes
  la t0,vsroot
  srli t0,t0,2
  ori t0,t0,0x53
  sd t0,0(t1)
  hfence.gvma
  hfence.vvma
  sret                      # retry the faulting guest fetch without skipping
finish:
  li t0,6
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x48595032
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

.balign 16384
groot:.skip 16384
glevel1:.skip 4096
gvsptes:.skip 4096

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
  la t0,gdata_l0
  srli t0,t0,2
  ori t0,t0,1
  li t2,2048
  add t1,t1,t2
  sd t0,0(t1)                # GPA 0x20000000 -> physical SRAM, U/R/W/X/A/D
  la t1,gdata_l0
  li t0,(0x80000000 >> 2) | 0xdf
  li t2,256
init_gdata:
  sd t0,0(t1)
  addi t1,t1,8
  addi t0,t0,1024
  addi t2,t2,-1
  bnez t2,init_gdata
  la t1,gdata_l0
  li t0,(0x800a4000 >> 2) | 0xdb
  sd t0,1312(t1)            # G-stage W denied on the second data page
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
  li t0,0xc0000000000000f0
  csrw henvcfg,t0
  li t0,0xc000000000000000
  csrw hstateen0,t0
  li t0,0x800a3ff0
  li t1,11
  sd t1,0(t0)
  li t1,22
  sd t1,8(t0)
  li t1,33
  sd t1,16(t0)
  li t1,44
  sd t1,24(t0)
  la t0,guest_entry
  li t1,0x40000000
  sub t0,t0,t1
  csrw sepc,t0
  li t0,0x180
  csrw hstatus,t0
  li t0,0x2300
  csrw sstatus,t0
  sret
guest_entry:
  li s0,0x400a3ff0
  li s1,0x400a4000
  vsetivli t0,4,e64,m2,tu,mu
  vmv.v.i v8,7
  li s7,1
vector_store:
  vse64.v v8,(s0)
  csrr t0,vstart
  bnez t0,guest_fail
  ld t0,0(s0)
  li t1,55
  bne t0,t1,guest_fail
  ld t0,8(s0)
  li t1,66
  bne t0,t1,guest_fail
  ld t0,0(s1)
  li t1,7
  bne t0,t1,guest_fail
  ld t0,8(s1)
  bne t0,t1,guest_fail
  vmv.v.x v16,t1
  li t0,99
  vmv.v.x v16,t0
  li s7,2
  li a0,0
  ecall                    # HS denies G-stage R for the second data page
vector_load:
  vle64.v v16,(s0)
  csrr t0,vstart
  bnez t0,guest_fail
  vmv.x.s t0,v16
  li t1,55
  bne t0,t1,guest_fail
  vslidedown.vi v24,v16,1
  vmv.x.s t0,v24
  li t1,66
  bne t0,t1,guest_fail
  vslidedown.vi v24,v16,2
  vmv.x.s t0,v24
  li t1,7
  bne t0,t1,guest_fail
  vslidedown.vi v24,v16,3
  vmv.x.s t0,v24
  bne t0,t1,guest_fail
  li s7,3
  li a0,0
  ecall                    # HS denies W for AMO and CBO faults
  li s7,4
  li t0,9
  amoadd.d t1,t0,(s1)
  li s7,5
  cbo.zero 0(s1)
  li s7,6
  li a0,1
  ecall
guest_fail:
  li a0,255
  ecall
1:j 1b
hs_trap:
  addi s6,s6,1
  csrr t0,hstatus
  andi t0,t0,0x180
  li t1,0x180
  bne t0,t1,fail
  csrr t0,scause
  li t1,10
  beq t0,t1,guest_call
  li t1,0x400a4000
  csrr t0,stval
  bne t0,t1,fail
  csrr t0,htval
  li t1,(0x200a4000 >> 2)
  bne t0,t1,fail
  csrr t0,htinst
  bnez t0,fail
  csrr t0,hstatus
  andi t0,t0,0x40
  beqz t0,fail
  li t0,1
  beq s7,t0,store_fault
  li t0,2
  beq s7,t0,load_fault
  csrr t0,scause
  li t1,23
  bne t0,t1,fail
  csrr t0,vstart
  bnez t0,fail
  li t0,0x800a4000
  ld t0,0(t0)
  li t1,7
  bne t0,t1,fail
  j skip_instruction
store_fault:
  csrr t0,scause
  li t1,23
  bne t0,t1,fail
  csrr t0,vstart
  li t1,2
  bne t0,t1,fail
  li t0,0x800a3ff0
  ld t1,0(t0)
  li t2,7
  bne t1,t2,fail
  ld t1,8(t0)
  bne t1,t2,fail
  ld t1,16(t0)
  li t2,33
  bne t1,t2,fail
  ld t1,24(t0)
  li t2,44
  bne t1,t2,fail
  li t1,55
  sd t1,0(t0)
  li t1,66
  sd t1,8(t0)
  la t0,gdata_l0
  li t1,(0x800a4000 >> 2) | 0xdf
  sd t1,1312(t0)
  hfence.gvma
  sret                     # same store PC, vstart=2
load_fault:
  csrr t0,scause
  li t1,21
  bne t0,t1,fail
  csrr t0,vstart
  li t1,2
  bne t0,t1,fail
  csrw vstart,zero
  vmv.x.s t0,v16
  li t1,55
  bne t0,t1,fail
  vslidedown.vi v24,v16,1
  vmv.x.s t0,v24
  li t1,66
  bne t0,t1,fail
  vslidedown.vi v24,v16,2
  vmv.x.s t0,v24
  li t1,99
  bne t0,t1,fail
  vslidedown.vi v24,v16,3
  vmv.x.s t0,v24
  bne t0,t1,fail
  li t0,0x800a3ff0
  li t1,111
  sd t1,0(t0)
  li t1,222
  sd t1,8(t0)
  la t0,gdata_l0
  li t1,(0x800a4000 >> 2) | 0xdf
  sd t1,1312(t0)
  hfence.gvma
  li t0,2
  csrw vstart,t0
  sret                     # same load PC; preserve completed destination elements
guest_call:
  li t0,255
  beq a0,t0,fail
  bnez a0,finish
  la t0,gdata_l0
  li t1,2
  beq s7,t1,deny_read
  li t1,(0x800a4000 >> 2) | 0xdb
  j install_pte
deny_read:
  li t1,(0x800a4000 >> 2) | 0xd9
install_pte:
  sd t1,1312(t0)
  hfence.gvma
skip_instruction:
  csrr t0,sepc
  addi t0,t0,4
  csrw sepc,t0
  sret
finish:
  li t0,6
  bne s7,t0,fail
  li t0,7
  bne s6,t0,fail
  lui t0,0x10000
  li t1,0x48595035
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
.balign 4096
gdata_l0:.skip 4096

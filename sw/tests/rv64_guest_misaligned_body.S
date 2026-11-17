/* This body uses the two-stage page tables initialized by the generated prologue. */
.equ LEFT_PA, 0x800a3ff8
.equ RIGHT_PA, 0x800b4000
.equ PAGE_GVA, 0x400a4000
.equ PAGE_GPA, 0x200a4000
.equ PTE_SLOT, 164*8
.equ LEFT_INITIAL, 0x1122334455667788
.equ RIGHT_INITIAL, 0x99aabbccddeeff00
.equ PAYLOAD, 0x89abcdef

.macro begin_guest_access
#if GUEST_MPRV
  li t4,0x1234
  csrw mtval2,t4
  csrr t5,mtval2
  bne t4,t5,fail
  li t4,0x3000
  csrw mtinst,t4
  csrr t5,mtinst
  bne t4,t5,fail
  li t4,GUEST_MSTATUS
  csrw mstatus,t4
#endif
.endm

.macro end_guest_access
#if GUEST_MPRV
  csrw mstatus,zero
#endif
.endm

.macro checkpoint phase
  li s7,\phase
#if GUEST_MPRV
  jal s10,guest_call
#else
  ecall
#endif
.endm

.macro check_words left, right
  li t0,LEFT_PA
  ld t1,0(t0)
  li t2,\left
  bne t1,t2,fail
  li t0,RIGHT_PA
  ld t1,0(t0)
  li t2,\right
  bne t1,t2,fail
.endm

.macro fault_pair store_cause, load_cause
  li s5,\store_cause
  la s8,1f
  begin_guest_access
1: sw s3,0(s0)
  end_guest_access
  li s5,\load_cause
  la s8,2f
  li t3,0x13579bdf
  begin_guest_access
2: lw t3,0(s0)
  end_guest_access
  li t0,0x13579bdf
  bne t0,t3,guest_fail
.endm

hs_entry:
  li t0,LEFT_PA
  li t1,LEFT_INITIAL
  sd t1,0(t0)
  li t0,RIGHT_PA
  li t1,RIGHT_INITIAL
  sd t1,0(t0)
#if GUEST_MPRV
  la t0,hs_trap
  csrw mtvec,t0
#else
  la t0,guest_entry
  li t1,0x40000000
  sub t0,t0,t1
  csrw sepc,t0
  li t0,GUEST_HSTATUS
  csrw hstatus,t0
  li t0,GUEST_SSTATUS
  csrw sstatus,t0
  sret
#endif

guest_entry:
  li s0,PAGE_GVA-2
  li s3,PAYLOAD
  begin_guest_access
  lw a2,0(s0)
  end_guest_access
  li t0,0xffffffffff001122
  bne a2,t0,guest_fail
  begin_guest_access
  sw s3,0(s0)
  lwu a3,0(s0)
  end_guest_access
  bne a3,s3,guest_fail
  checkpoint 1
  fault_pair 23,21
  checkpoint 2
  fault_pair 15,13
  checkpoint 3
#if GUEST_MPRV
  fault_pair 7,5
  checkpoint 4
  fault_pair 7,5
  checkpoint 5
#endif
guest_fail:
  checkpoint 255
1:j 1b

hs_trap:
#if GUEST_MPRV
  csrr t0,mstatus
  srli t1,t0,38
  andi t1,t1,3              # Actual V=0 is saved in MPV, even with effective guest access.
  li t2,1
  bne t1,t2,fail
  srli t1,t0,11
  andi t1,t1,3
  li t2,3
  bne t1,t2,fail
  li t0,0x8000020000
  csrc mstatus,t0
  csrr t0,mcause
  bne t0,s5,fail
  csrr t0,mepc
  bne t0,s8,fail
  csrr t0,mtval
  li t1,PAGE_GVA
  bne t0,t1,fail
  csrr t0,mtval2
  bne t0,s9,fail
  csrr t0,mtinst
  bnez t0,fail
#else
  csrr t0,hstatus
  andi t0,t0,0x180
  li t1,GUEST_HSTATUS
  bne t0,t1,fail
  csrr t0,scause
  li t1,GUEST_ECALL
  beq t0,t1,guest_call
  bne t0,s5,fail
  csrr t0,sepc
  bne t0,s8,fail
  csrr t0,stval
  li t1,PAGE_GVA
  bne t0,t1,fail
  csrr t0,htval
  bne t0,s9,fail
  csrr t0,htinst
  bnez t0,fail
  csrr t0,hstatus
  andi t0,t0,0x40
  beqz t0,fail
#endif
  check_words LEFT_INITIAL,RIGHT_INITIAL
  addi s6,s6,1
#if GUEST_MPRV
  addi t0,s8,4
  csrw mepc,t0
  mret
#else
  j skip
#endif

guest_call:
  li t0,1
  beq s7,t0,break_g
  li t0,2
  beq s7,t0,break_vs
#if GUEST_MPRV
  li t0,3
  beq s7,t0,deny_g_table
  li t0,4
  beq s7,t0,deny_vs_table
  li t0,5
  bne s7,t0,fail
  li t0,8
#else
  li t0,3
  bne s7,t0,fail
  li t0,4
#endif
  bne s6,t0,fail
  check_words LEFT_INITIAL,RIGHT_INITIAL
  lui t0,0x10000
  li t1,0x48535054
  sw t1,0xc(t0)
  sw zero,0x14(t0)
  j 1b
break_g:
  bnez s6,fail
  check_words 0xcdef334455667788,0x99aabbccddee89ab
  li t0,LEFT_PA
  li t1,LEFT_INITIAL
  sd t1,0(t0)
  li t0,RIGHT_PA
  li t1,RIGHT_INITIAL
  sd t1,0(t0)
  la t0,gdata_l0
  sd zero,PTE_SLOT(t0)
  hfence.gvma
  li s9,PAGE_GPA >> 2
  j resume_guest
break_vs:
  li t0,2
  bne s6,t0,fail
  la t0,gdata_l0
  li t1,(0x800b4000 >> 2) | 0xdf
  sd t1,PTE_SLOT(t0)
  hfence.gvma
  la t0,vslevel0
  sd zero,PTE_SLOT(t0)
  hfence.vvma
  li s9,0
  j resume_guest
#if GUEST_MPRV
deny_g_table:
  li t0,4
  bne s6,t0,fail
  la t0,vslevel0
  li t1,(PAGE_GPA >> 2) | GUEST_PTE_FLAGS
  sd t1,PTE_SLOT(t0)
  la t0,gdata_l0
  j deny_table_entry
deny_vs_table:
  li t0,6
  bne s6,t0,fail
  la t0,vslevel0
deny_table_entry:
  /* Deny only the second page's 8-byte PTE, with an allow-all lower-priority entry. */
  addi t0,t0,PTE_SLOT
  srli t0,t0,2
  csrw pmpaddr0,t0
  li t0,0x1f18
  csrw pmpcfg0,t0
  hfence.gvma
  li s9,0
#endif
resume_guest:
#if GUEST_MPRV
  jr s10
#else
skip:
  csrr t0,sepc
  addi t0,t0,4
  csrw sepc,t0
  sret
#endif
fail:
  lui t0,0x10000
  slli t1,s7,8
  or t1,t1,s6
  sw t1,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j 1b

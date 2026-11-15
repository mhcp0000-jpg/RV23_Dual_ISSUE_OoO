# Project contract

Work in this directory. The original My_core project is a read-only provenance
source for this effort; do not resume its timing-candidate queues here.

The active user target is RV32IMFC_Zicsr_Zifencei, M/U modes. The previous
RVA23S64 plan has been superseded by the user's RV32 instruction. RV32 is not
an RVA23 profile. Track current requirements in docs/RV32_TARGET.md; the old
RVA23 gap document is historical. Do not advertise unsupported ISA features.

Current hardware: rv23_soc_top, default XLEN32, 32-bit physical addresses,
I-cache 32 KiB + D-cache 32 KiB, 64-byte lines, main AXI bus and shared SRAM
1 MiB, CLINT/PLIC machine interrupts, native halt/drain/resume and debug AXI.
Standard RISC-V Debug Module/JTAG and L2 are future work. core_run_i is initial
boot/reset control and must not abort a running AXI transaction.
Each L1 has two 64-bit banks (address bit 3), 32 KiB total. Native 128-bit IF
hits and different-bank dual LSU hits must preserve one-cycle bank reads.
Main AXI remains 64-bit. The D-cache merges authoritative accepted SRAM write
bytes into resident lines; I-cache snoops invalidate code lines. Different
words of a line must not await an unrelated write-through response.

Keep source lists consistent. Maintain import provenance and source hashes with
python scripts/check_manifest.py --update, then check without --update.
Use scripts/run_checks.py for directed validation. The reports identify smoke
coverage; they are not full ISA, performance or synthesis sign-off. Preserve
separate original/new project timing claims. Do not copy generated build output
or former test PASS claims into the source tree as new validation.
The full RV32 objective additionally requires scripts/run_all_rv32_checks.py
and scripts/audit_rv32_release.py: original block/backend cases, sequence-credit
pressure and its pre-fix control, exact FP, ELF/CoreMark, bus lock controls and
seeded memory tests. The three baseline smoke tests alone do not complete it.

Use synchronous active-low reset for control state. SRAM payload is not reset
cleared; invalidate tags/valid state instead. Hold ready/valid payloads stable
under backpressure. Stores become visible only after architectural commit, and
write-through completion must wait for the system-bus response. MMIO never
allocates into cache. Changes to coherence, FENCE.I, atomics or debug resume
must include tests for races, ownership and stale state.

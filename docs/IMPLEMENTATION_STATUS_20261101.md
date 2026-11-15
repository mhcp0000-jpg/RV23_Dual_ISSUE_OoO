# 2026-11-01 implementation checkpoint

The active target remains the complete official RVA23S64 profile. The current
RTL contains the scalar, S/MMU, vector, H/Sha and HPM paths described in
[RVA23_TARGET.md](RVA23_TARGET.md). This checkpoint does not declare complete
profile compliance. A normative requirement-by-requirement audit and full
architectural/differential validation remain open.

- All 64 implemented-feature checks passed against the current source inputs.
- The renewed RV32 release passed its six gates: 58 block/backend cases,
  22 ELF programs, boot/cache/memory and three seeded scoreboards, negative
  controls, exact-ELF performance and retirement-control comparisons.
- Six native H/HPM ELFs passed on one H-enabled RV64 SoC. They include two-stage
  VS/G translation, HLV/HSV/HLVX, MPRV+MPV, HUPMM, VS/VU traps, virtual timer and
  injected software interrupts, partial vector fault/restart, AMO/CBO faults,
  filtered counters and overflow interrupts.
- Native vector streams passed 733 integer, 235 FP and 8,660 Bare-memory
  packets, plus S-mode and guest precise partial-state/restart tests.
- Directed timing evidence passed 16 identical-text scalar fixtures with
  408 measured instructions and 84,348 paired vector probes across 231 forms.
  A data-dependent VCLZ early-exit mutation was rejected.
- The preserved original TIM ELF was executed again without rebuilding it:
  576,450 timed instructions and 513,076 cycles on the current cached RV32 SoC.
  The older TIM timing remains historical evidence, not a fresh TIM run.

The implementation fixed guest-to-HS fetch authority at redirects, xRET's
immediate-interrupt return boundary, 64-bit CLINT timer accesses and the single
LCOFIP pending-bit owner. Aligned vector PBMT IO is permitted as complete-size
uncached transfers; split accesses entering IO fault before element effects.

Current reports: `out/rva23/functional_checkpoint.json`,
`out/rva23/hypervisor_checkpoint.json`, `out/rva23/timing_contract_evidence.json`,
`out/rv32_release_audit.json` and `docs/verification_snapshot.json`.
The separately sealed H/V/HPM/timing source checkpoint is
`out/checkpoints/hypervisor_hpm_20261101`; its SCOPE describes its validation
boundary and the earlier publication state at capture time.

Next: compare every mandatory RVA23U64/RVA23S64/Sha requirement with concrete
RTL and current tests, implement any uncovered behavior and run architectural
validation. Broader memory-ordering and timing coverage remain separate from
these finite directed checks. Native halt/drain/debug AXI is connected;
standard external Debug Module/JTAG and Linux/platform bring-up remain separate
platform work. No synthesis/STA or official CoreMark score is claimed.

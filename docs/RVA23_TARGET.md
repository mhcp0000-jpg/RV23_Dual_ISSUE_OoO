# Active target: complete RVA23S64

On 2026-10-29 the user explicitly selected the complete official RVA23S64
profile, including V, H, S mode and MMU. This supersedes the RV32-only target.
Implement functionality first; keep IPC optimization separate.
Track the implementation order and final validation in the
[RVA23S64 implementation checklist](RVA23_IMPLEMENTATION_CHECKLIST.md).

The checkpoint after the HS `sie` fix passed 70 feature steps and the six-gate
RV32 release. The RV64 H/V SoC also passed a direct issue/execute/retire
observation: independent younger ALUs bypass a stalled divider dependency,
dual issue/execution/retirement occur, all ten target instructions retire in
program order and their 64-bit results match the oracle. The content-bound
pipeline/commit audit is `out/rva23/rv64_ooo/audit.json`. It includes 104
instruction-bank pairs, two next-cycle dual D-cache responses, and eight
64-bit AXI reads to refill the tested SRAM line.
The HS `sie` fix limits it to delegated HS interrupt bits. A same-ELF
test reproduced the spurious virtual external interrupt on the previous model
and passed HS/VS delivery on the corrected model. Full regression, ACT4 and
boot results for that revision are tracked in the implementation checklist.
The latest `hgatp` fix preserves MODE and writes the aligned root PPN when
software requests an unsupported MODE. The saved CSR ELF fails case 218 on
the old model and passes on the corrected SoC. The [current checklist](RVA23_IMPLEMENTATION_CHECKLIST.md)
tracks the new regression, ACT4 and Linux replay.
The preceding privileged checkpoint includes breakpoint GVA and the base
16-entry PMP CSR group (eight usable entries), 390 native privilege cases,
642 precise traps, 33 breakpoint contexts and ten MPRV fault cases. The older
68-step and seven-fix checkpoints remain preserved under `out/checkpoints`.

The committed CSR component passed 1,971 checks. Twenty-five saved scalar
ELFs, including all 5,261 FP oracle cases, passed on the same H/V-enabled SoC
without rebuilding. In addition, 168 identical functional ELFs passed Sail
and RTL; all 152 user ISA traces matched across 61,754 retirements. This is
finite independent evidence, not complete architectural certification. See
[IMPLEMENTATION_STATUS_20261102](IMPLEMENTATION_STATUS_20261102.md),
[RVA23_REQUIREMENT_AUDIT](RVA23_REQUIREMENT_AUDIT.md),
[UPSTREAM_ISA_TESTS](UPSTREAM_ISA_TESTS.md) and [SAIL_REFERENCE](SAIL_REFERENCE.md).

Normative target: [RVA23 Profiles 1.0](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html).
All 663 selected ACT4 4.1.0 checked-in tests and 2,083 generated vector ELFs
passed again with the same ELFs after the HS `sie` fix. The vector ELFs fit
within 1 MiB, including 20 built with a 32 KiB
test stack. The execution audit binds the RTL, model, ELF and log hashes and
includes the ADD-to-SUB failure control. Full normative coverage remains open.
The reference is Sail 0.16 because ACT4's pinned 0.13.1 lacks H.
The detailed scope and evidence are in [ACT4_VERIFICATION](ACT4_VERIFICATION.md).

The minimal Linux platform milestone passed in an isolated 32 MiB simulation:
Linux 6.12 entered S mode, executed U-mode `/init`, emitted its success marker
and powered off with host exit code zero. The replay after the Svpbmt fix used
the same kernel Image and passed its audit in `out/linux_bringup/pbmt_fixed/boot_audit.json`.
The replay after the HS `sie` fix passed with the same loadable firmware at
`out/linux_bringup/hs_sie_fixed/boot_audit.json`.
The OpenSBI handoff probe in `tb/fixtures/opensbi` exercises the production 1 MiB SoC with its own
DTB, supervisor entry, SBI timer call and supervisor timer interrupt.
Linux RV64 requires a 2 MiB aligned kernel entry. With resident firmware at
`0x80000000`, the usual next aligned entry at `0x80200000` lies outside the
1 MiB SRAM window. [Linux RISC-V boot requirements](https://docs.kernel.org/arch/riscv/boot.html)
`baselines/rv32_verified_20261029` preserves the prior source and report records.
Prior RV32 PASS results are not RVA23 evidence.

| Mandatory area | Current implementation/evidence | Remaining work |
|---|---|---|
| RV64I, M, C, F, Zicsr, Zifencei | Integrated RV64 decoder/execution/CSR/fetch paths, directed native tests and pinned upstream I/M/C/F suites | Complete architectural/differential testing |
| B (Zba/Zbb/Zbs), Zicond | Decode/ALU/pipeline implemented; 14,087 direct vectors and 246 integrated RV64 cases passed | Full architectural suite and renewed RV32 release regression |
| A, Za64rs, Zawrs, Ziccrse, Ziccamoa | W/D LR/SC and AMO at ROB head; AXI exclusives/per-ID 64-byte monitors/debug snoops; 672 direct checks, 243 integrated AMO oracle cases, 459 atomic retirements; Sv39 fault tests; WRS STO/NTO and U TW timeout passed | Full forward-progress, memory-ordering and architectural test audit |
| D, Zfhmin, Zfa | Integrated 64-bit FP PRF/writeback, H/S/D load/store boxing, compressed D, HardFloat arithmetic and profile conversion/Zfa instructions; 38,469 direct issue/result vectors, 5,261 full-core oracle cases, all 8,192 compressed D encodings, FS/SD and Sv39 fault tests passed | Complete architectural suite, H/VS state interactions and renewed RV32 regression |
| V, Zvfhmin, Zvbb, Zvkt | VLEN128/ELEN64 owner integrated with decode/CSR/ROB, integer/FP operations, masks/reductions/permutations and unit/stride/index/segment/whole/mask/FF memory. Native streams: 825 integer, 235 FP, 8,660 Bare-memory packets; VS/FS/SD and Sv39 fault/restart ELFs passed. Natural aligned elements use one full-size transfer and full-size PMP checks | Guest partial-fault restart now passed; 84,348 paired timing probes passed; broader timing and full architectural verification |
| Zicntr, Zihpm, Zkt | Cycle/time/instret plus four 64-bit HPM counters, committed event selectors and M/HS/VS/VU permissions; mode filtering and overflow integrated | 16 identical-text native timing fixtures passed; broader timing/architectural coverage |
| Zimop, Zcmop, Zcb, Zihintpause, Zihintntl | All 40 Zimop forms and compressed extensions integrated; GNU canonical oracle 1,008 RV32/1,016 RV64 vectors and all 65,536 compressed encodings checked per XLEN; hints use legal inert operations | Broader architectural tests and remaining hint audit |
| Zic64b, Zicbom, Zicbop, Zicboz | 64-byte ZERO through main AXI, real I/D invalidate/flush and drained write-through clean; U CSR permissions, read-only/D-bit Sv39 faults, pointer masking and prefetch-hint tests passed | Full race/PMA/ordering suite and broader H virtual-permission cases |
| Ziccif, Zicclsm | ROB-head hardware assist for ordinary integer/FP misalignment; original LSQ ownership retained until retirement, younger loads replayed; 67 integrated scalar boundary cases. Vector element prevalidation, natural single-request accesses, misalignment and nonadjacent Sv39 W/D/PBMT fault/restart checks passed | Guest context connected; complete ordering and broader concurrent-agent race coverage |
| Supm, Ssnpm | Senvcfg PMM WARL 0/7; integrated Bare/Sv39 tests for LSU/FP/A, MPRV, MXR disable, transformed tval and unmasked fetch passed | Native U HUPMM/HLVX and MPRV+MPV tests; broader VS/VU vector/CMO masking coverage |
| Ss1p13, Ssu64xl, Svbare, Sv39, Svade | S CSR/delegation/SRET and Sv39 translation before LSU commit implemented; integrated M/S/U and seven precise page-fault cases passed | Complete privileged architecture audit and tests |
| Ssccptr, Sstvecd, Sstvala, Sscounterenw | Physical PTE reads use PMP and main cached AXI path; trap values/counter permissions implemented | Full contract coverage |
| Svpbmt, Svinval, Svnapot | PBMT and 64-KiB NAPOT; Svinval real Sv39 remapping/retry, HINVAL execution in HS with two-stage translation, and TVM/U permission tests passed | Additional attribute and fence race combinations |
| Sstc, Sscofpmf | Sstc virtual timer/time-offset IRQ and HPM OF/mode filters/scountovf/LCOFI integrated, including native HS/guest overflow | Broader timer, counter and interrupt architectural tests |
| Sha: H, Ssstateen, Shcounterenw, Shvstvala, Shtvala, Shvstvecd, Shvsatpa, Shgatpa | H bank/stateen and guest scalar/FP/A/CBO/V paths integrated; native VS Sv39 + G Sv39x4, guest faults/retry, virtual timer/software IRQ, MPRV/HUPMM/HLVX tests | Native guest partial vector load/store restart and AMO/CBO faults passed; broader virtual-permission and architectural/differential coverage |
| Requested SoC/debug | I/D 32 KiB, two 64-bit banks per cache, AXI64, SRAM1MiB, PLIC/CLINT, native halt/AXI trace | Standard Debug Module/JTAG and L2 remain future work outside the mandatory profile |

Completion requires all mandatory areas integrated and tested on the same
RV64 SoC. Optional extensions are not silently added to the profile scope.
Functional implementation, architectural validation and timing sign-off are
separate statuses; none may be inferred from the other.

Evidence is content-bound under `out/rva23/`. A later RTL edit makes an earlier
report historical until its affected tests are rerun. Scalar functional checks
do not establish V, H, full profile compliance or synthesis timing closure.

Timing implementation evidence is in [TIMING_CONTRACT](TIMING_CONTRACT.md).
All 69 implemented-feature checks passed after the privileged audit fixes. The complete
RV32 release audit also passed its six gates, including 58 block/backend cases,
22 ELF programs, boot/cache/seeded tests, negative controls and exact-ELF
performance/retirement checks. See [IMPLEMENTATION_STATUS_20261102](IMPLEMENTATION_STATUS_20261102.md).

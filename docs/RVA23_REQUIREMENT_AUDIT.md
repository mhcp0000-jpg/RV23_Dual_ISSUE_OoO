# RVA23S64 normative audit

The remaining review queue is [RVA23_REMAINING_REVIEW](RVA23_REMAINING_REVIEW.md),
generated from `config/rva23_clause_review_index.json`. It links RV64I and all
58 mandatory names to 22 groups and 52 open review topics. These are review
tasks, not a defect count or an exhaustive clause inventory. The required
`audit_clause_review_index.py` gate checks omissions, duplicates, document
links, status consistency and content hashes; it does not judge architectural
sufficiency or establish profile completion.

The required-name inventory is `config/rva23_required_extensions.json`, checked
against the official RVA23 Profiles 1.0 page and its recorded HTML SHA-256.
There are 58 unique mandatory extension names when the eight Sha components
are expanded, plus the RV64I/little-endian base requirements. Aggregate extension
dependencies and non-instruction contracts must be audited as well.

The combined audit records a row for RV64I and each of the 58 required names
under `evidence.requirement_execution` in `out/rva23/requirement_traceability.json`.
It counts passing ACT4 cases by literal tag, lists related subset tags for
A/B/C and the supervisor ISA, and binds separate execution reports to the
specific behaviors they exercise. The directed links are maintained in
`config/rva23_execution_evidence.json`. All 59 rows have execution evidence,
and 24 have a literal checked-in ACT4 requirement tag. These counts describe
the scope of the executed tests. The clause review continues in
`RVA23_PROFILE_CONTRACT_REVIEW.md`.

The sealed 68-step feature checkpoint and six-gate RV32 release passed.
Neither result alone proves all clauses of each required extension. The active
goal remains the full official RVA23S64 implementation.
The follow-up guest-breakpoint GVA fix passed its 33-case native metadata matrix;
the expanded 69-step checkpoint and renewed six-gate RV32 release passed.

`config/rva23_implementation_map.json` now maps all 58 names, plus the RV64I
base, to 21 implementation groups with compiled RTL paths and executable check
drivers. `scripts/audit_rva23_requirements.py` validates this traceability;
`--with-evidence` additionally requires the current 70-step feature checkpoint,
the same-ELF H/V replay, MPRV fault metadata and pinned Sail comparison evidence.
This is a structural/evidence audit, not a proof that every normative clause is
covered.

The 2026-11-02 permission/CSR audit found and fixed these concrete omissions:

| Contract | Previous behavior | Implemented correction / evidence |
|---|---|---|
| Svinval ordering fences in VU | Illegal instruction, cause 2 | Virtual instruction, cause 22; native privilege matrix |
| U WFI with S-mode and TW=0 | Retired then slept beyond a 400,000-cycle watchdog | Immediate cause 2; VU TW=0 remains cause 22, machine TW retains cause-2 priority |
| Mandatory mconfigptr | Legal M read trapped | Hardwired-zero read; writes and lower-privilege accesses trap |
| M/S/H FIOM with paging | All three fields were hardwired zero | Writable FIOM; existing conservative FENCE/AMO serialization already orders all memory classes |
| mip.SEIP CSRRS/CSRRC | External SEIP could be copied into software pending state | Read returns B\|E, RMW uses software B only; external deassertion no longer leaves a software interrupt |
| Non-delegated S interrupts targeting M | SEI/SSI/STI could select interrupt cause 0 | Preserve causes 9/1/5 with architectural M-target priority; all 127 nonempty physical interrupt combinations and upstream vectored-interrupt execution |
| Guest breakpoint trap GVA | Nonzero guest PC written to tval with GVA clear | Address-trap classification includes breakpoints and instruction-address misalignment; 33 M/HS/VS delegation/form cases, including C.EBREAK and GVA clearing for illegal instructions |
| Base 16-entry PMP CSR group | pmpaddr8..15 trapped despite the lower group being present | Expose unused entries as WARL zero with ignored writes, retaining eight usable comparators; committed CSR test passed 1,971 checks; 140 added PMP cases expand the matrix to 390 cases/642 traps; all 69 feature steps and six RV32 gates passed |

Pre-fix native/component sources, executables or bound model records, ELFs and
failure traces are preserved under `out/negative_controls/`. The expanded CSR
test exhausts 320 privilege/intercept contexts and 960 SRET/SFENCE/WFI checks,
then tests committed FIOM and SEIP behavior. The native matrix additionally
checks real decode, retirement, precise instruction trap values and returns.
All 25 saved scalar-profile ELFs, including 5,261 embedded FP oracle cases,
were replayed without rebuilding on the same H/V-enabled SoC used for H and V.
An additional native ELF passed eight MPRV+MPV guest faults (explicit accesses
and implicit VS-PTE reads, effective VS/VU, loads/stores) and two ordinary-M
controls. It checks GVA, actual-mode MPP/MPV, mtval2 and mtinst, including the
implicit-PTE pseudoinstruction and M-level handling despite medeleg settings.

The pinned Sail model and current H/V core additionally passed 168 identical
functional ELFs. Exact retirement comparison passed all 152 user ISA ELFs,
61,754 instructions, including full 64-bit integer/FP results. The copied-trace
high-bit corruption control was rejected. This adds independent differential
evidence while full ACT4 and broader privileged/vector-state comparison remain
open. See [SAIL_REFERENCE](SAIL_REFERENCE.md).

Remaining audit actions:

1. Extend the completed implementation map with finer normative-clause coverage,
   identifying missing or weak evidence rather than inferring it from feature bits.
2. Audit profile-defined contracts, especially naturally aligned instruction
   atomicity, reservation geometry/eventual progress, coherent PTE reads,
   precise S/VS/HS trap values and writable counter-enable fields.
3. Audit all Ss1p13 and H architectural state/permission/return requirements,
   including contexts not yet reached by the directed native ELFs.
4. Extend the pinned upstream self-checking ISA regressions and add full
   architectural/differential testing; implement any uncovered behavior.
   Keep optional platform work separate from the profile's mandatory set.

[Official RVA23 Profiles 1.0](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html)

## Current execution evidence (2026-11-11)

After the Svpbmt precedence fix, the 70-step checkpoint, six RV32 release
gates and 2-issue OoO fixture passed again. The corrected H/V SoC passed
168 identical Sail ELFs. The audit compared 61,754 retirement records
across 152 user ELFs and 2,554 events across 16 privileged ELFs, and
rejected the renewed corruption and omission controls. The source-bound
requirements audit with --with-evidence passed. The combined integration
audit passed with ACT4, 1 MiB OpenSBI and 32 MiB Linux evidence for that revision.

Run the combined audit for the HS `sie` revision with
`python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant hs_sie_fixed`.
It rechecks the ACT4, RV32, 1 MiB OpenSBI probe, 32 MiB Linux boot, OoO,
memory and vector execution artifacts, including the Zkt/Zvkt timing mutation.
The OpenSBI check binds the S-mode, DTB and timer success marker to the
current RTL, simulator binary, firmware ELF and clean simulator exit. It
also checks the probe trace for two S-mode ECALLs and the supervisor timer
interrupt, and records the trace hash. The timing check recomputes the scalar
retirement schedule from ELF symbol bounds and
matches the vector latency records to the request stream. The report
`out/rva23/requirement_traceability.json` records those audit hashes and
record counts. The timing comparison covers the data and configurations
described in [TIMING_CONTRACT](TIMING_CONTRACT.md).

The Linux audit compares both the kernel Image and the generated DTB with
their bytes in loadable segments of the OpenSBI ELF. It records the DTB hash
and its load address, S-mode entry, user-mode retirement, the `/init` marker,
the kernel power-down message and the simulator's successful exit.
A separate hash covers the ELF entry and loadable segment layouts and bytes.

If the Linux simulator exits on a host timeout after its model and firmware
were built, rerun the same variant with the existing artifacts:

```text
python scripts/run_opensbi_handoff.py --linux-image out/linux_bringup/kbuild-native/arch/riscv/boot/Image --variant pbmt_fixed --reuse-build --boot-timeout 43200
```

The retry validates the saved firmware, kernel, DTB and model before launch
and uses the same 100,000,000 simulated-cycle limit.

After rebuilding the H/V SoC, run the directed contract fixtures again with
python scripts/audit_profile_contracts.py --rerun. The audit checks each
new report against the current RTL, executable, ELF and trace before continuing.

`scripts/run_guest_context_restore.py` reuses the VS page-table setup
from the basic hypervisor fixture. A VS ECALL enters HS with vector and
FP state dirty. The HS handler spills all 32 vector and 32 FP registers,
overwrites the hardware state, and restores the registers and five CSRs.
It uses whole-register V loads and stores and the [VSETVL context restore
sequence](https://docs.riscv.org/reference/isa/unpriv/v-st-ext).
After SRET, the guest compares 64 vector words, 32 FP words and
VL, VTYPE, VSTART, VCSR and FCSR. The trace contains two VS ECALLs.
The source, ELF, trace and log hashes are recorded in
`out/rva23/guest_context_restore/report.json`.

`scripts/run_hlvx_permissions.py` reuses the existing VS and G page-table
setup and exercises 35 permission cases with HLV and both HLVX forms.
The fixture checks the [H extension permission rules](https://docs.riscv.org/reference/isa/priv/hypervisor.html).
The 32-case matrix crosses execute-only and read-only PTEs at each stage with
all four HS/VS MXR combinations for HLV.D and HLVX.WU. Three controls check
HLVX.HU and physical PMP denial when either read or execute permission is
absent. Nineteen expected traps verify cause, SEPC, STVAL, HTVAL, GVA and SRET
continuation. The contract audit checks the execution artifacts under
`out/rva23/hlvx_permissions`.

`scripts/run_hypervisor_access_widths.py` extends the existing HUPMM
and HU permission fixture on the full RV64 H/V SoC. In HS and HU-enabled
U mode it checks seven HLV forms, four HSV sizes and both HLVX forms.
The signed loads use values with the sign bit set. Each store checks the
entire containing 64-bit word to detect stray byte writes. The U-mode
HLV/HSV cases use tagged addresses and HLVX uses an untagged address.
All 26 data checks and the original four trap checks passed. The report
with source, ELF, trace and log hashes is under
`out/rva23/hypervisor_access_widths/report.json`.

`scripts/run_rv64_platform_contract.py` derives an RV64 fixture from the
existing RV32 platform test and runs it on the full H/V SoC. The fixture
checks MXL, wrong-path store suppression and FENCE.I after modifying code.
It handles CLINT software and timer interrupts in M mode, claims and
completes PLIC source 1 in both contexts, and handles a delegated Sstc
timer interrupt. The commit trace has causes 3, 7, 11, 5 and 9 in order.
The testbench checks native halt, drain, AXI reads and writes while halted,
and retirement after resume. The source, ELF, trace and log hashes are
recorded in `out/rva23/rv64_platform_contract/report.json`.

`scripts/run_vector_fp_differential.py` runs three identical ELF pairs on Sail
and the current RV64 H/V RTL. The fixtures exercise single and double vector
add, divide and multiply, plus Zvfhmin half widening and narrowing across
all five rounding modes. Whole-register stores expose the destination group
to scalar reads at 40 checkpoints. The trace comparison checks the full
destination data and CSR reads. Explicit flag expectations cover invalid,
divide by zero, overflow, underflow and inexact. The report records hashes
of the ELF, traces, model reports and configuration under
`out/rva23/vector_fp_differential/report.json`.
The combined audit runs `run_vector_fp_differential.py --check` to validate
the saved inputs and rerun the trace comparison.

The vector-state differential follow-up uses 22 identical ELF pairs across
the legal SEW/LMUL combinations of the implemented VLEN128/ELEN64 configuration.
Each pair has five checkpoints: initialized state, masked ADD with vstart=1,
saturating ADD at shortened VL, a zero-VL XOR, and gather with vstart=1.
Tail and mask policies are undisturbed, making all observed bits defined.
At every checkpoint all 32 registers are whole-stored and read as 64 scalar
LD results. Sail and the current full H/V RTL matched 7,040 vector words,
770 CSR values and 38,918 complete trace events. Explicit checks cover VL,
VTYPE, VSTART, all four VXRM values, sticky VXSAT/VCSR and VLENB=16.
A copied trace with snapshot bit 63 flipped is rejected at the changed event.
`scripts/audit_vector_state_differential.py` independently rechecks the current
model/runtime/library/source/ELF/trace/log inputs, exact 22-case membership,
whole-load/store counts, all snapshots/CSRs, comparisons and corruption control.
Evidence is in `out/rva23/vector_state_differential/{report,audit}.json`.
This is exact integer/undisturbed state coverage and complements ACT and the
existing directed FP/agnostic/guest-fault cases; it does not claim differential
coverage of those latter contexts.

The follow-up `scripts/run_vector_agnostic_differential.py` reuses the 22
fixtures with each of the three remaining VTA/VMA policies. The audit confirms
that only the policy bits in five VSETVLI instructions differ in each ELF's
loaded segments. The [V 1.0 tail/mask rules](https://docs.riscv.org/reference/isa/unpriv/v-st-ext)
define the allowed value sets: the checker independently calculates active
results and tests prestart, undisturbed, agnostic and VL=0 state for each model
before comparing trace events. All 66 cases passed (330 snapshots, 21,120
64-bit vector words, 2,310 CSR values and 116,754 events). Both actual models
matched exactly. A copied state and a full copied trace with a legal all-ones
tail choice were accepted; four copies with illegal tail/prestart/active/VL=0
changes were rejected. `scripts/audit_vector_agnostic_differential.py` binds
and rechecks the source/ELF/trace/log, model inputs and controls. Reports are in
`out/rva23/vector_agnostic_differential`. This closes the data-destination policy
matrix for the selected operations; mask-destination rules, FP and guest
fault/restart are outside this particular comparison.

The corrected RTL passed that 66-case comparison again. A separate Sail
comparison passed 40 FP result and flag checkpoints across e16, e32 and e64.
The integer owner and full RV64 H/V SoC each passed 825 packets with the
expanded mask-destination stream. The added `vmsltu.vx` cases observe all
128 destination bits for each VTA/VMA policy after masked execution with
`vstart=2`, zero VL, and `vstart=vl`. The test checks the RTL's permitted
choice to preserve inactive bits and the mask tail.

The profile-added contracts now have a finer source/evidence review in
[RVA23_PROFILE_CONTRACT_REVIEW](RVA23_PROFILE_CONTRACT_REVIEW.md). It separates
each reviewed condition from the broader base-ISA, V, H and Ss1p13 audits.
The implementation map links the supplemental LR/SC, fetch atomicity, PTE
coherence, CSR/counter, split-fetch, OoO and event-trace drivers to their
existing mandatory groups; the target's mandatory-name set is unchanged.

The split-fetch follow-up executes a 32-bit instruction at VA `0x40000ffe`
whose second parcel faults at `0x40001000`. Twelve S/VS cases and 24 precise
traps passed, covering M/HS/VS destinations, page/PMP access faults and two
G-stage guest-page faults. Handlers separately check xepc at the instruction
start and xtval at the failing parcel, GVA/MPV/SPV and xRET return. The two
G-stage cases also check shifted guest PA `0x80041000` in htval/mtval2.
`scripts/audit_profile_contracts.py` now checks current source/model/runtime
and source/ELF/trace/log hashes, exact case membership and recorded fault
PC/address/cause for this report at `out/rva23/split_fetch_faults/report.json`.

The full production RV64 H/V SoC additionally passed a direct dual-issue/OoO
integration fixture, `scripts/run_rv64_ooo_integration.py`. The divider issues
at cycle 249; younger independent ALUs start issuing at 250 while the older
dependent ADD cannot issue until 315. Six younger-ready selections occur while
the divider is busy. The fixture observes four dual issue, four dual execute
and four dual retire cycles, with all ten measured instructions retiring in
program order and producing exact full-width 64-bit results. The independent
post-run audit reconstructs these observations from the pipeline CSV and the
architectural commit trace, rather than only accepting a PASS string. Current
evidence is `out/rva23/rv64_ooo/{report,audit}.json`; run the audit with
`scripts/audit_rv64_ooo_integration.py`. This checks the requested microarchitecture
on the full RV64 configuration and is separate from IPC benchmark measurements.

The production RTL passed the 70-step feature checkpoint and all six RV32
release gates after the Svpbmt fix. The checkpoint passed again with the
expanded vector mask test. All 663 checked-in and 2,083 generated vector
ACT4 ELFs passed again after the Svpbmt fix. The ADD-to-SUB control failed as
expected. The rerun reused the same ELFs. The runner
keeps prior passes only when the model, ELF and log hashes agree, reruns failed
or timed-out cases, and replaces the progress report after each completed case.
Sail 0.16 remains an explicit exception to ACT4's reference pin.

`scripts/run_lrsc_progress.py` additionally checks W/D accesses at all 24
naturally aligned positions within one 64-byte reservation granule, with the
four-instruction LR/ADDI/SC/BNEZ retry region starting at instruction-line
offsets 0, 32 and 62. The current full H/V SoC passed all 72 placements and
1,152 successful updates in 1,152 SC attempts. Retirement traces confirm the
requested widths and actual instruction-line positions. This strengthens
Ziccrse evidence for constrained loops, including split instruction fetch;
it does not prove progress under all arbitration or external-writer schedules.
See `out/rva23/lrsc_progress/report.json` and the
[constrained-loop requirements](https://docs.riscv.org/reference/isa/unpriv/a-st-ext.html).

The native counter permission matrix now covers 960 cases: M/HS/VS/U/VU,
all eight M/H/S gate combinations, cycle/time/instret/HPM3..6 and RAZ HPM31,
and low-half reads, RV64 high-half reads, and read-only writes with zero.
All 1,793 expected traps passed, including machine cause-2 priority over guest
cause-22 interception. Each trap checks instruction tval, PC, MPP/MPV and
return; all three enable CSRs are read back after writes. The implemented
seven enable bits also passed an all-ones write/readback. The test is
`scripts/run_counter_permission_matrix.py --form read|high|write_zero` (three
separate invocations so each ELF retains the original 128 KiB code layout).
The expected rules come from the
[H counter-enable and virtual-instruction rules](https://docs.riscv.org/reference/isa/priv/hypervisor.html).
This supplies Sscounterenw/Shcounterenw and counter-access evidence for these
contexts, not a complete H/CSR-state audit. `scripts/audit_profile_contracts.py`
checks current RTL/model/runtime inputs and source/ELF/trace/log hashes, exact
case membership, and the LR/SC placement report. Its result is
`out/rva23/contract_evidence.json`.

`scripts/run_profile_csr_geometry.py` passed 279 M-mode CSR roundtrip checks
on the same H/V SoC. S/VS trap-vector registers each preserved 76 aligned bases
in the canonical Sv39 low/high ranges, including walking address bits and range
endpoints, with Direct mode. The test separately checks Bare/Sv39 in satp and
vsatp, Bare/Sv39x4 in hgatp, and UXL=64 in physical/virtual supervisor status.
An unsupported satp/vsatp MODE preserves the whole register. An unsupported
hgatp MODE preserves MODE and updates the aligned root PPN. The earlier
geometry oracle incorrectly required hgatp to preserve the whole register.
Current RTL register assignments preserve vector BASE bits
and accept Direct mode; translation MODE support is symmetrical for satp and
vsatp. These checks strengthen Sstvecd, Shvstvecd, Shvsatpa, Shgatpa, Svbare,
Sv39 and Ssu64xl evidence. They complement the existing actual trap/page-walk
tests and do not establish every address or translation behavior by themselves.
All four S and all four H state-enable CSRs also passed native read/write
roundtrips, with H SE/ENVCFG masks and S read-as-zero state matching the
absence of optional sstateen-controlled state. This checks the eight required
Ssstateen views in the integrated core, supplementing their component gates.
The current contract evidence audit also binds this report and its artifacts.

`scripts/run_ptw_debug_coherence.py` passed a new full H/V SoC test for Ssccptr:
external debug AXI updates a resident leaf PTE, then S-mode SFENCE.VMA and
an actual page walk must observe the new mapping. Sixteen remaps cover both
32/64-bit debug writes and eight halted/eight running-core updates. The monitor
observed 17 walker leaf responses (one cold initial translation), 16 real PTW
cache hits and 16 resident snoops. The software checks the resulting page data.
A copied cache with snoop updates disabled only at the tested PTE address fails
at the first remap with the old PTE. The ELF and TB are identical for this
failure control; production RTL is unchanged. The current hash/membership audit
is `scripts/audit_ptw_debug_coherence.py --with-negative`, with evidence under
`out/rva23/ptw_debug_coherence` and `out/negative_controls/ptw_debug_coherence`.
This checks ordered external updates and fence visibility, not all concurrent
page-walk/PTE-writer schedules or a universal memory-ordering proof.

An unmasked comparison of the previously executed privileged Sail/RTL traces
additionally found exact matching prefixes for 14 of the 16 M/S ELFs, totaling
2,085 instructions. `scripts/probe_sail_privileged_retirements.py` records PC,
raw instruction, trap/cause, integer/FP destination and full 64-bit writeback
comparisons without masking CSR values. The two remaining streams first differ
at an interrupt entry (`rv64mi/illegal`) and WFI (`rv64si/wfi`); the existing Sail
trace callback emits rows only when an instruction was fetched and the step is
not waiting, whereas the RTL trace includes these events. They remain recorded
as differences, not exact matches or evidence of an RTL defect. The independent
self-checking ELF runs still passed all 16. No existing trace or reference
executable was modified in this probe.

The follow-up `scripts/build_sail_event_driver.py` links a separate host driver
against the same existing Sail model/runtime/SoftFloat libraries. Its observer
records fetched WFI even when the step waits and traps that occur before fetch,
with an explicit interrupt flag and low cause code. The bounded execution loop
is byte-identical to the original except for the callback header include.
`scripts/run_sail_event_comparison.py` then reran all 16 unchanged privileged
ELFs on this driver and compared against their current, hash-bound RTL traces.
All 2,554 event prefixes matched PC, raw instruction, trap/cause and full scalar
integer/FP writeback without masking CSR values. Removing the interrupt event
from `rv64mi/illegal` or waiting WFI from `rv64si/wfi` in copied traces causes a
mismatch at the removed position. `scripts/audit_sail_event_comparison.py`
rechecks all artifacts, compiler/runtime/generated-model/library inputs,
case membership, comparisons and both omission controls. Evidence is under
`out/rva23/sail_privileged_events`; its audit passed. This closes those two
trace-alignment differences, not all privileged architectural/state coverage.

The 1 MiB SoC after the Svpbmt fix passed the upstream OpenSBI S-mode/DTB/timer probe.
The audit checked two SBI calls and a supervisor timer interrupt in the
retire trace. The simulator retired 4,070,386 instructions and exited with
code zero. Evidence is under `out/opensbi_handoff_htif`.

The Svpbmt-corrected RTL booted the same Linux 6.12 Image in the 32 MiB simulation.
The first U-mode retirement was at `0x100b0`. The program printed
`RV23 LINUX INIT PASS` and Linux powered off with host exit code zero.
The simulator reported 21,655,063 commits. The audit in
`out/linux_bringup/pbmt_fixed/boot_audit.json` verifies the Image and DTB
embedded in firmware and the source, simulator and console hashes for that run.

After the HS `sie` fix, the same-ELF interrupt isolation regression and the
combined execution audit passed. The audit includes 25 scalar ELF replays,
all 2,746 ACT4 ELFs, the 1 MiB OpenSBI probe and the 32 MiB Linux replay with
`/init` and orderly power-off. The report is `out/rva23/requirement_traceability.json`.
See the [HS interrupt CSR check](RVA23_PROFILE_CONTRACT_REVIEW.md#csr-쓰기와-sret-직후-인터럽트).

## Current hgatp revision

The same CSR geometry ELF failed case 218 before the fix and passed all 279
cases after it. The current RTL passed the 70-step functional checkpoint, six
RV32 release gates, 663 checked-in ACT4 cases, 2,083 generated vector ACT4
cases and 40 supplemental H/Sv39x4/PMP cases. The ADD-to-SUB negative control
was rejected. The combined integration audit passed with execution evidence
for all 59 rows covering RV64I and the 58 mandatory named requirements.

The 1 MiB SoC passed the original OpenSBI handoff ELF. The 32 MiB Linux 6.12
demonstration reused the same OpenSBI ELF, Linux Image and DTB before and after
the CSR change. Both executions retired 21,822,717 instructions. The current
boot audit records S-mode entry, the U-mode vector instruction, successful
`/init` vector computation and orderly power-off in
`out/linux_bringup/hgatp_vector/boot_audit.json`.

The separate Linux 6.14 run additionally checks the userspace `prctl` path
for PMLEN 0→7→0 and scalar/vector memory accesses through a tagged pointer.
Use the integration audit with that run to require the Supm evidence.

```powershell
python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm
```

[Linux 6.14 console excerpt](evidence/linux-supm-boot-2026-11-17.txt)

The clause audit now includes the Sscofpmf `scountovf` visibility matrix and
the Sstc timer compare read/write permission matrix. See the
[profile contract review](RVA23_PROFILE_CONTRACT_REVIEW.md) for the executed
conditions and the clauses still open.

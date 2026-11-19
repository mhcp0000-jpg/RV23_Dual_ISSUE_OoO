# RVA23S64 남은 규격 검토

이 문서는 `config/rva23_clause_review_index.json`에서 생성한 검토 작업 목록이다.
RV64I와 필수 확장 58개를 포함한 59개 요구사항, 22개 구현 그룹과
46개 미완료 검토 주제를 연결한다. 이는 결함 46개라는 뜻이 아니다.
또한 완전한 규격 조항 목록이나 구현·검증 완료 판정표가 아니다.

각 주제를 닫을 때는 규격 조항, 실제 RTL 경로, 실행·예외·상태·순서의 근거와
허용된 구현 선택을 해당 검토 문서에 남긴다. 새 실패가 있으면 RTL 수정과
원래 실패를 재현하는 검사 및 관련 회귀를 완료한다. 구현 선택으로 충족하면
그 이유를 기록한다. 단순 테스트 개수나 확장 이름으로 종료하지 않는다.

인덱스 검사는 요구사항 누락·중복, 문서 연결, 상태 일관성과 현재 파일 해시를
확인한다. 검토 내용의 논리적 충분성을 자동으로 판정하지 않는다. 모든 작업이
목록에서 사라져도 이 검사만으로 전체 프로파일 달성을 선언할 수 없다.

| 그룹 | 요구사항 | 열린 주제 | 현재 검토 |
|---|---|---:|---|
| base | I | 1 | [RVA23_INTEGER_CLAUSE_REVIEW.md](RVA23_INTEGER_CLAUSE_REVIEW.md), [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |
| muldiv | M | 0 | [RVA23_INTEGER_CLAUSE_REVIEW.md](RVA23_INTEGER_CLAUSE_REVIEW.md) |
| atomics | A, Za64rs, Ziccrse, Ziccamoa | 2 | [RVA23_ATOMIC_CLAUSE_REVIEW.md](RVA23_ATOMIC_CLAUSE_REVIEW.md) |
| scalar_fp | F, D, Zfhmin, Zfa | 3 | [RVA23_FP_CLAUSE_REVIEW.md](RVA23_FP_CLAUSE_REVIEW.md) |
| bitmanip | B, Zicond | 2 | [RVA23_BITMANIP_CLAUSE_REVIEW.md](RVA23_BITMANIP_CLAUSE_REVIEW.md) |
| compressed | C, Zimop, Zcmop, Zcb | 2 | [RVA23_C_CLAUSE_REVIEW.md](RVA23_C_CLAUSE_REVIEW.md), [RVA23_ZCB_CLAUSE_REVIEW.md](RVA23_ZCB_CLAUSE_REVIEW.md), [RVA23_MOP_CLAUSE_REVIEW.md](RVA23_MOP_CLAUSE_REVIEW.md) |
| csr_counters | Zicsr, Zicntr, Zihpm | 2 | [RVA23_ZICSR_CLAUSE_REVIEW.md](RVA23_ZICSR_CLAUSE_REVIEW.md), [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |
| ifetch | Ziccif | 2 | [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |
| misaligned | Zicclsm | 2 | [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md), [RVA23_INTEGER_CLAUSE_REVIEW.md](RVA23_INTEGER_CLAUSE_REVIEW.md), [RVA23_FP_CLAUSE_REVIEW.md](RVA23_FP_CLAUSE_REVIEW.md) |
| hints | Zihintpause, Zihintntl, Zicbop | 0 | [RVA23_CMO_CLAUSE_REVIEW.md](RVA23_CMO_CLAUSE_REVIEW.md), [RVA23_INTEGER_CLAUSE_REVIEW.md](RVA23_INTEGER_CLAUSE_REVIEW.md), [RVA23_HINT_CLAUSE_REVIEW.md](RVA23_HINT_CLAUSE_REVIEW.md) |
| cmo | Zic64b, Zicbom, Zicboz | 3 | [RVA23_CMO_CLAUSE_REVIEW.md](RVA23_CMO_CLAUSE_REVIEW.md) |
| scalar_timing | Zkt | 2 | [TIMING_CONTRACT.md](TIMING_CONTRACT.md) |
| vector | V, Zvfhmin, Zvbb, Zvkt | 4 | [RVA23_VECTOR_CLAUSE_REVIEW.md](RVA23_VECTOR_CLAUSE_REVIEW.md), [TIMING_CONTRACT.md](TIMING_CONTRACT.md), [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |
| wrs | Zawrs | 2 | [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |
| pointer_mask | Supm, Ssnpm | 2 | [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |
| fencei | Zifencei | 0 | [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md), [RVA23_FENCEI_CLAUSE_REVIEW.md](RVA23_FENCEI_CLAUSE_REVIEW.md) |
| supervisor | Ss1p13, Svbare, Sv39, Svade, Ssccptr | 3 | [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |
| supervisor_profile | Sstvecd, Sstvala, Sscounterenw, Ssu64xl | 2 | [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |
| page_extensions | Svpbmt, Svinval, Svnapot | 3 | [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |
| timer | Sstc | 2 | [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |
| hpm | Sscofpmf | 2 | [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |
| hypervisor | Sha, H, Ssstateen, Shcounterenw, Shvstvala, Shtvala, Shvstvecd, Shvsatpa, Shgatpa | 5 | [RVA23_PROFILE_CONTRACT_REVIEW.md](RVA23_PROFILE_CONTRACT_REVIEW.md) |

## base: RV64I base execution and EEI

- [ ] `base.2` — Review instruction/data access atomicity and RVWMO rules against the actual platform paths.
- [x] `base.1` — Map ECALL/EBREAK and defined illegal instruction metadata to the base clauses.

검토 결론: Base ECALL/EBREAK and defined illegal metadata mapped to decode/head completion, precise ROB/CSR trap delivery and non-retirement. A same-ELF five-mode 100-case delegation matrix checks original EPC/tval, counter deltas and preserved values, complementing the existing breakpoint GVA/return matrix. Memory atomicity and RVWMO remain under base.2.

근거: [RVA23_INTEGER_CLAUSE_REVIEW.md](RVA23_INTEGER_CLAUSE_REVIEW.md)


## muldiv: RV64 M

이 작업 목록에 남은 검토 주제 없음. 연결 문서의 실제 근거와 한계를 확인한다.

- [x] `muldiv.1` — Complete current-target reserved encoding and zero-destination disposition.

검토 결론: Current-target OP/OP-32 M encoding partitions and rd=x0 destination suppression reviewed through decoder cleanup. Native 13-form zero-destination cases and 36 reserved-word precise traps complement the existing independent arithmetic results; active-flush ownership is reviewed separately under muldiv.2.

근거: [RVA23_INTEGER_CLAUSE_REVIEW.md](RVA23_INTEGER_CLAUSE_REVIEW.md)

- [x] `muldiv.2` — Connect multiply/divide issue, recovery and retirement ownership to the instruction contracts.

검토 결론: Issue/data/tag binding, selective/full wrap-aware flush, live-result arbitration, matching ROB completion and architectural rename commit reviewed in the production source. New XLEN64 active/held ownership component scenarios complement the existing production RV64 issue/execute/retire witnesses; no universal schedule claim.

근거: [RVA23_INTEGER_CLAUSE_REVIEW.md](RVA23_INTEGER_CLAUSE_REVIEW.md)


## atomics: A and reservation contracts

- [ ] `atomics.2` — Map access-fault, misalignment and permission priority for LR, SC and AMO.
- [ ] `atomics.3` — Document the constrained-loop progress argument under the platform arbitration assumptions.
- [x] `atomics.1` — Review the exclusive read-modify-write retry path against interfering accepted writes.

검토 결론: Exclusive read/write retry reviewed through engine old-value recomputation, ID/address/size monitors, accepted-write invalidation, failed-exclusive no-write and serialized successful target ownership. A production-component AXI interference matrix covers 270 cases and 243 failed attempts; whole-core AMO value and drain evidence remain complementary. Fault priority and constrained progress stay open.

근거: [RVA23_ATOMIC_CLAUSE_REVIEW.md](RVA23_ATOMIC_CLAUSE_REVIEW.md)


## scalar_fp: F/D/Zfhmin/Zfa

- [ ] `scalar_fp.1` — Map current-target legal/reserved format and rounding encodings to decode and trap paths.
- [ ] `scalar_fp.2` — Review naturally aligned FP transfer atomicity and memory-fault metadata.
- [ ] `scalar_fp.3` — Connect precise commit and cancellation of FPR/flags to trap and interrupt ownership.

## bitmanip: B/Zicond

- [ ] `bitmanip.1` — Map defined/reserved RV64 bitmanip encodings in the enabled target configuration.
- [ ] `bitmanip.2` — Review the two-source syntactic dependency path for Zicond separately from value and timing tests.

## compressed: C/Zcb/MOP

- [ ] `compressed.1` — Consolidate the current-target compressed legal/HINT/reserved encoding partition.
- [ ] `compressed.2` — Map original compressed instruction and PC length preservation through fetch/data traps.

## csr_counters: CSR and base counters

- [ ] `csr_counters.1` — Enumerate CSR bank privilege, alias and WARL dispositions for the current target.
- [ ] `csr_counters.2` — Review cycle/time/instret update and counter-enable behavior against all mandatory counter clauses.

## ifetch: Instruction fetch atomicity

- [ ] `ifetch.1` — Review the aligned parcel argument for resident hits and every refill beat placement.
- [ ] `ifetch.2` — Connect accepted-store snoops, refill ownership and frontend invalidation to instruction visibility.

## misaligned: Main-memory misaligned accesses

- [ ] `misaligned.1` — Map split translation and protection prechecks for all enabled ordinary transfer widths.
- [ ] `misaligned.2` — Review partial-store prevention, fault address and non-idempotent memory restrictions.

## hints: PAUSE/NTL/prefetch hints

이 작업 목록에 남은 검토 주제 없음. 연결 문서의 실제 근거와 한계를 확인한다.

- [x] `hints.1` — Close the hint decode and no-memory-request argument in the current target.

검토 결론: Ignored NTL/prefetch use rd=x0 integer paths without LSU, CSR or CBO classification; PAUSE uses the existing FENCE drain path. Current-target decode, extension overrides and head classification reviewed with the cited snapshot/Sail evidence.

근거: [RVA23_HINT_CLAUSE_REVIEW.md](RVA23_HINT_CLAUSE_REVIEW.md)

- [x] `hints.2` — Separate architectural hint behavior from optional microarchitectural actions and timing.

검토 결론: The specifications permit ignoring NTL/prefetch and permit PAUSE to wait for outstanding memory completion. Optional cache allocation, power and performance effects are separated from architectural state and the independent Zkt/Zvkt timing evidence.

근거: [RVA23_HINT_CLAUSE_REVIEW.md](RVA23_HINT_CLAUSE_REVIEW.md)


## cmo: Cache block operations

- [ ] `cmo.1` — Review management operation authority over all coherent cache copies.
- [ ] `cmo.2` — Map translation/PMP/PMA and permission-fault priority for each CBO.
- [ ] `cmo.3` — Connect write-response, invalidation and concurrent accepted-write ownership to the CMO ordering clauses.

## scalar_timing: Zkt timing

- [ ] `scalar_timing.1` — Confirm the mandated scalar timing instruction inventory against enabled dependencies.
- [ ] `scalar_timing.2` — Review that data values cannot select a different completion path for each required instruction family.

## vector: V/Zvfhmin/Zvbb/Zvkt

- [ ] `vector.1` — Complete the required integer/FP/reduction/mask/permutation instruction and reserved-encoding clause map.
- [ ] `vector.2` — Review EEW/EMUL, overlap, segment partial completion and restart restrictions by memory family.
- [ ] `vector.3` — Map vector CSR WARL and context transitions to the state clauses.
- [ ] `vector.4` — Complete the timing source-path argument for the mandated Zvkt families.

## wrs: Wait on reservation

- [ ] `wrs.1` — Review timeout, trap interception, interrupt and debug wake conditions by privilege context.
- [ ] `wrs.2` — Map reservation-set loss and subsequent SC behavior to both WRS forms.

## pointer_mask: User/supervisor pointer masking

- [ ] `pointer_mask.1` — Review effective privilege and HUPMM/MPRV/MPV selection for each affected access path.
- [ ] `pointer_mask.2` — Map masking exclusions, transformed trap addresses and PMM WARL behavior to the pointer-masking clauses.

## fencei: Instruction-fetch synchronization

이 작업 목록에 남은 검토 주제 없음. 연결 문서의 실제 근거와 한계를 확인한다.

- [x] `fencei.1` — Review FENCE.I ordering from older accepted stores to future instruction fetch.

검토 결론: FENCE.I reaches completion only after older committed stores receive responses and LSU accepted traffic/translations drain. Serializing ROB and head ownership preserve the explicit-memory boundary; source and native self-modifying execution reviewed.

근거: [RVA23_FENCEI_CLAUSE_REVIEW.md](RVA23_FENCEI_CLAUSE_REVIEW.md)

- [x] `fencei.2` — Connect resident/refilling I-cache and frontend invalidation completion to retirement.

검토 결론: The I-fabric idle input is constant, so correctness uses retire-driven invalidate, killed refills that cannot install valid tags, retained response epochs, and architectural frontend redirect/target-buffer invalidation. Both source priority rules and current race/self-modifying execution evidence reviewed.

근거: [RVA23_FENCEI_CLAUSE_REVIEW.md](RVA23_FENCEI_CLAUSE_REVIEW.md)


## supervisor: Ss1p13/Bare/Sv39/Svade/PTE coherence

- [ ] `supervisor.1` — Inventory mandatory S and supporting M CSRs, WARL fields and privilege access rules.
- [ ] `supervisor.2` — Map trap/delegation/return and status transitions to the supervisor clauses.
- [ ] `supervisor.3` — Review Sv39 page walk, A/D faults, implicit PTE permissions and coherent PTE visibility.

## supervisor_profile: Supervisor profile contracts

- [ ] `supervisor_profile.1` — Review all required direct trap-vector bases and precise trap-value dispositions.
- [ ] `supervisor_profile.2` — Map implemented counter-enable writability and fixed UXL64 to the profile conditions.

## page_extensions: PBMT/NAPOT/invalidation

- [ ] `page_extensions.1` — Review PBMT attribute composition and ordering for host and two-stage guest accesses.
- [ ] `page_extensions.2` — Map NAPOT legal/reserved leaf encodings and implicit read restrictions.
- [ ] `page_extensions.3` — Review Svinval permission, address/ASID scope and ordering of the conservative invalidation implementation.

## timer: Sstc

- [ ] `timer.1` — Review compare update, pending recomputation, timer wrap and htimedelta arithmetic.
- [ ] `timer.2` — Map direct/alias CSR gating and timer interrupt routing for S/VS/U/VU contexts.

## hpm: Sscofpmf

- [ ] `hpm.1` — Review counter increment filters, overflow state and interrupt pending ownership.
- [ ] `hpm.2` — Map scountovf visibility and implemented HPM event/WARL behavior.

## hypervisor: Sha/H/Ssstateen and guest profile contracts

- [ ] `hypervisor.1` — Inventory H/VS CSR aliases, WARL and state-enable hierarchy.
- [ ] `hypervisor.2` — Review virtual trap entry/return, delegation and interrupt priority rules.
- [ ] `hypervisor.3` — Map HLV/HSV/HLVX privilege, execute permission and access-fault metadata.
- [ ] `hypervisor.4` — Review VS/G-stage walk and implicit fault metadata including hgatp/vsatp mode contracts.
- [ ] `hypervisor.5` — Map HFENCE/HINVAL ordering and guest trap-vector/value/counter profile conditions.

## 갱신·재검사

```text
python scripts/audit_clause_review_index.py --write
python scripts/audit_clause_review_index.py
python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm
```

검토 내용은 인덱스와 연결 문서를 함께 수정하고 첫 명령으로 이 문서를 갱신한다.
보고서는 `out/rva23/clause_review_index_audit.json`에 있으며 전체 목표는 활성 상태다.

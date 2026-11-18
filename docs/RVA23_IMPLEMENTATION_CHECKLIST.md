# RVA23S64 기능 구현 체크리스트

완료 기준은 같은 RV64 2-issue OoO SoC에서 필수 ISA와 특권 동작을 실행하고, 마지막에 ACT와 별도 케이스를 통과하는 것이다. 기본 구성은 L1 I/D 각 32 KiB, 캐시당 64비트 뱅크 2개, AXI64, SRAM 1 MiB, PLIC, CLINT, 기존 halt/drain/debug AXI다.

- [x] 공식 프로파일의 RV64I 리틀엔디언과 필수 확장 58개를 컴파일되는 RTL에 매핑했다. 개별 RTL 경로와 테스트는 `config/rva23_implementation_map.json`에 기록했다. 아래 항목은 규격 조항별 구현 확인과 수정이 남은 작업이다. [RVA23 Profiles 1.0](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html)

## 1. RTL 기능 마무리

- [x] production RV64 H/V SoC에서 2-issue와 OoO 실행을 직접 관찰했다. `scripts/run_rv64_ooo_integration.py`의 나눗셈은 249사이클에 issue, 그 결과에 의존하는 명령은 315사이클에 issue됐다. 뒤의 독립 ALU 명령은 250사이클부터 먼저 issue/execute됐고, divider가 busy인 동안 younger-ready bypass가 6회 있었다. dual issue·dual execute·dual retire를 각각 4회 관찰했다. 대상 10개 명령은 프로그램 순서대로 retire하고 64비트 결과 10개가 Python oracle과 일치했다. `scripts/audit_rv64_ooo_integration.py`가 실제 pipeline/commit CSV에서 순서·동시 처리 횟수·결과를 다시 계산했다. 이는 기능 지향성 테스트이며 IPC 성능 기준은 아니다.

| 상태 | 구현 항목 | 완료 조건 |
|---|---|---|
| 구현 및 지향성 확인 | MMIO store와 분기 복구의 동시 처리 | ROB 헤드의 device store가 정상 응답과 younger flush를 같은 사이클에 받아도 버스에 한 번만 쓰고 다음 사이클에 retire한다. 오류 응답은 원래 store의 정확한 예외가 된다. |
| 구현 및 지향성 확인 | Sstc의 M/HS/VS 접근 제한 우선순위 | `mcounteren.TM` 또는 `menvcfg.STCE`가 꺼졌으면 VS/VU의 직접 `vstimecmp` 접근은 cause 2다. M 설정이 허용하는 경우에만 게스트에서 가로챌 수 있는 접근에 cause 22를 낸다. |
| 구현 및 지향성 확인 | 벡터 segment의 재시작 가능한 물리 접근 | segment 단위 `vstart`에서 재실행될 수 있는 MMIO와 PBMT=IO 필드를 버스 요청 전에 차단한다. 일반 SRAM, 단일 필드, fault-only-first 길이 단축을 별도로 확인한다. |
| 수정 및 실행 확인 | 2단계 Svpbmt 우선순위 | VS-stage가 PBMT를 지정하면 최종 메모리 유형으로 사용하고, VS가 0이면 G-stage 값을 사용한다. 수정 전에는 VS=NC/G=IO에서 IO가 반환됐다. |
| 확인 필요 | RV64I/M/A/F/D/C/B와 추가 스칼라 확장 | 적법한 명령은 실제 실행·writeback·retire 경로까지 연결하고, 미지원 인코딩·잘못된 boxing·FP 플래그를 처리한다. Zimop/Zcmop 및 locality hint는 규격이 허용한 동작을 사용한다. |
| 확인 필요 | V, Zvfhmin, Zvbb | 모든 필수 연산과 EEW/EMUL 조합, 마스크·tail, `vstart`와 fault-only-first, segment 부분 완료, VS/VU 재시작을 확인한다. 미구현 경로를 찾으면 실행 엔진과 precise trap 경로까지 연결한다. |
| 확인 필요 | Ss1p13, S/H, Sv39 및 G-stage | CSR 권한과 WARL, trap/delegation/return, S/VS/HS trap 값과 카운터 권한, PMP/PBMT/NAPOT, S/H fence와 재시작을 확인한다. HFENCE/HINVAL 경로는 이미 연결돼 있다. |
| 확인 필요 | 메모리 계약 | 32비트 정렬 fetch의 원자성, 64B 캐시 블록, coherent PTE read, LR/SC reservation과 eventual progress, misaligned load/store, CBO 및 디버그 snoop의 순서를 확인한다. |
| 확인 필요 | 카운터, 타이머 및 지연 계약 | Sstc와 Sscofpmf의 M/HS/VS/VU 동작, Zkt/Zvkt의 피연산자 독립 지연을 확인한다. |
| 실행 확인 | 플랫폼 통합 | RV64 H/V SoC에서 CLINT MSIP/MTIP, M/S PLIC claim/complete, Sstc의 S 타이머, 디버그 halt/drain/resume을 실행했다. 근거는 `out/rva23/rv64_platform_contract/report.json`에 있다. |

## 2. 기능을 증명하는 별도 케이스

- [x] RV64M의 하위·상위 곱, 부호 조합, W형의 하위 입력과 부호 확장, 0 나누기 및 signed overflow 조항을 RTL과 연결했다. 기존 전체 H/V 실행에서 13개 명령의 피연산자를 복원해 결과 296개를 Python 정수 계산으로 확인하고, 잘못된 결과 13개를 거부했다. `scripts/audit_rv64m_contract.py`를 통합 감사에 포함했다. 전 피연산자·pipeline 스케줄 증명은 아니며 다른 스칼라 확장의 검토를 대신하지 않는다.

- [x] 지연된 스칼라 DIV 의존 분기의 잘못된 경로에 여섯 종류의 벡터 명령을 배치했다. 실제 speculative dispatch와 flush를 관찰하고 벡터 실행·retire/trap이 발생하지 않음을 검사했다. 올바른 경로의 메모리·벡터·설정·스칼라 상태가 보존됐고 동일 ELF의 Sail과 두 RTL 실행에서 이벤트 291개가 일치했다. `scripts/run_vector_branch_order.py --check`와 통합 순서 감사에서 재검사한다.

- [x] 실제 분기 오예측 복구 사이클에 MMIO 응답을 넣었다. 수정 전 RTL은 응답을 소비해 실패했고 수정 후는 쓰기 1회와 정상 retire를 통과했다. 기존 DECERR 정확한 예외 검사도 통과했다.
- [x] Sstc의 M 권한 두 비트 조합과 VS/VU의 직접·별칭 CSR 접근을 24개 추가했다. 수정 전 RTL의 잘못된 cause 22를 검출했고 수정 후 전체 CSR 케이스 102개를 통과했다.
- [x] `run_privileged_instruction_matrix.py --group sstc`로 같은 전체 SoC에서 M/HS/VS/U/VU의 직접·별칭 CSR 접근 160개와 정확한 trap 279개를 통과했다. 동일 ELF를 수정 전 모델에서 실행하면 66번 케이스에서 실패한다.
- [x] vector segment의 MMIO, PBMT=IO, fault-only-first, 단일 필드 대조를 포함해 메모리 패킷 9,119개를 통과했다. 수정 전 RTL은 PBMT=IO 필드에서 필요한 접근 예외 없이 완료해 실패했다.
- [x] 변경 RTL을 전체 RV64 H/V SoC로 빌드해 기본 H/게스트 명령, VS 타이머·소프트웨어 인터럽트, G-stage 벡터 부분 fault와 재시작의 세 통합 테스트를 통과했다.
- [x] 기존 특권 명령 매트릭스 390개와 정확한 trap 642개를 변경 RTL에서 다시 통과했다.
- [ ] ACT가 직접 검사하지 않는 V 부분 fault/restart, H/VS trap metadata 및 권한, 캐시/AXI/PMA 순서와 동시 접근, Zkt/Zvkt를 기존 지향성 테스트와 대조하고 빠진 조합만 추가한다.
- [x] Ziccif 지향성 케이스에서 64바이트 I-cache 라인의 정렬된 32비트 위치 16개를 검사했다. 각 위치에서 디버그 AXI 쓰기와 해당 라인의 refill이 29회씩 겹쳤다. retire한 명령은 쓰기 전후 인코딩 중 하나였고, 최종 쓰기 뒤 `FENCE.I`를 실행한 후 새 명령이 retire했다. 실행은 `scripts/run_instruction_fetch_atomicity.py`를 사용한다.
- [x] 같은 production H/V SoC에서 LR/SC의 W/D 정렬 주소 24개와 반복문의 I-cache 라인 위치 3개를 조합한 72개 배치를 실행했다. 각 배치가 16회 갱신해 총 1,152회 성공했고 SC 시도도 1,152회였다. 라인 끝 62바이트 위치의 32비트 LR 명령은 실제로 다음 라인에 걸쳐 retire했다. `scripts/run_lrsc_progress.py`와 `out/rva23/lrsc_progress/report.json`은 유한 실행 근거이며 보편적인 진행성 증명은 아니다.
- [x] `scripts/run_counter_permission_matrix.py --form read|high|write_zero`의 세 실행에서 M/HS/VS/U/VU, M/H/S enable 8개 조합, cycle/time/instret/HPM3..6과 RAZ HPM31을 검사했다. 전체 960개 케이스와 1,793개 정확한 trap을 통과했다. M 차단 cause 2, 게스트 H/S 차단 cause 22, RV64 high-half 접근과 읽기 전용 CSR의 zero 쓰기 cause 2를 검사했다. CSR enable readback과 trap의 PC·명령 tval·MPP/MPV도 검사했다. `scripts/audit_profile_contracts.py`는 이 근거와 LR/SC 근거를 현재 RTL·모델·ELF·trace·로그 해시에 대조한다.
- [x] `scripts/run_profile_csr_geometry.py`의 M 모드 CSR 검사 279개를 같은 H/V SoC에서 통과했다. S/VS trap-vector 각각 76개 정렬된 주소의 Direct 모드 readback을 확인했다. `satp`/`vsatp`의 Bare·Sv39와 `hgatp`의 Bare·Sv39x4를 읽고, 미지원 MODE에서 `satp`/`vsatp`는 전체 값을, `hgatp`는 MODE를 유지하는지 확인했다. 물리/가상 S 상태의 UXL=64와 `sstateen0..3`/`hstateen0..3`의 존재·쓰기·WARL readback도 확인했다.
- [x] `scripts/run_ptw_debug_coherence.py`로 외부 debug AXI가 resident PTE를 수정한 뒤 S 모드의 `SFENCE.VMA`와 실제 page walk가 새 값을 읽는지 통과했다. 16회 remap(코어 정지 8회·실행 중 8회), 64/32비트 쓰기, 실제 walker 응답 17회(최초 cold miss 포함), PTW cache hit 16회와 resident snoop 16회를 확인했다. `scripts/check_ptw_debug_coherence_negative.py`는 해당 PTE의 snoop update만 제거한 캐시 복사본에서 같은 ELF/TB로 첫 remap의 stale PTE를 검출했다. `scripts/audit_ptw_debug_coherence.py --with-negative`의 현재 소스·모델·ELF·trace·로그 해시 대조도 통과했다. 이는 외부 쓰기와 fence로 순서를 정한 S-mode 사례이며 모든 동시 page-walk 경합의 증명은 아니다.
- [x] 변경 RTL의 70단계 기능 회귀와 RV32 릴리스 게이트 6개가 모두 통과했다. 기존 TIM 성능 ELF의 SHA-256도 보존본과 일치한다.
- [x] 기존 Sail trace에서 빠졌던 interrupt-before-fetch와 waiting WFI를 별도 observer에서 기록했다. 원본 model/driver/ELF/trace는 보존했고, 같은 Sail 라이브러리와 기존 RTL trace에서 특권 ELF 16개·2,554개 이벤트의 PC/명령/trap/cause/64비트 scalar writeback이 모두 일치했다. 인터럽트/WFI 이벤트를 제거한 두 복사본은 해당 위치에서 거부했다. `scripts/audit_sail_event_comparison.py`의 현재 아티팩트 해시·케이스·실제 비교·누락 검출 대조도 통과했다. 전체 특권 상태나 사이클 동등성 증명은 아니다.
- [x] `scripts/run_split_fetch_faults.py`에서 페이지 경계에 걸린 32비트 명령의 뒤쪽 parcel fault를 검증했다. HS/VS 실행과 M/HS/VS trap 대상, page/access 및 G-stage guest-page fault를 조합한 12개 사례·24개 trap이 통과했다. `xepc=0x40000ffe`, `xtval=0x40001000`, GVA와 복귀를 검사했고, G-stage는 뒤쪽 parcel GPA의 shifted htval/mtval2도 확인했다. 현재 contract evidence audit에 연결했다.
- [x] `scripts/run_vector_state_differential.py`의 같은 ELF를 Sail/RTL에서 실행했다. VLEN128/ELEN64의 legal SEW/LMUL 22개 조합에서 5개 checkpoint마다 전체 32개 V register를 whole-store하고 scalar LD로 관찰했다. tail/mask undisturbed, `vstart=1`, masked add, 짧은 VL의 saturating add, VL=0, gather 이후 상태를 검사해 7,040개 64비트 값·CSR 값 770개·전체 trace 38,918개가 일치했다. VXRM 4개 값과 sticky VXSAT도 확인했고, snapshot word의 bit 63을 바꾼 복사본은 거부했다. `scripts/audit_vector_state_differential.py`의 현재 소스·모델·ELF·trace·로그 해시와 실제 비교 대조가 통과했다. 이 새 비교는 integer/undisturbed 상태 범위이며 FP·agnostic 선택·guest fault/restart 전체의 differential 검증은 아니다.
- [x] `scripts/run_vector_agnostic_differential.py`로 나머지 세 VTA/VMA 정책 × 22개 SEW/LMUL, 총 66개 사례를 통과했다. 각 ELF의 실행 payload는 기존 5개 `vsetvli`의 정책 비트만 달랐다. 330개 snapshot의 V register 값 21,120개와 CSR 2,310개, trace 이벤트 116,754개를 대조했다. 개별 element의 active·prestart·mask-off·tail·VL=0 조건을 검사한 뒤 비교했으며 실제 두 모델의 snapshot 차이는 0이었다. 허용된 all-ones 선택 2개를 받아들였고 tail/prestart/active/VL=0의 잘못된 변경 4개를 거부했다. `scripts/audit_vector_agnostic_differential.py`가 현재 실행 근거를 대조했다. 범위는 해당 integer data-destination 연산이며 mask-result의 별도 tail 규칙은 이 케이스에 포함하지 않는다.

- [x] 기존 Zkt/Zvkt 시험의 현재 RTL과 실행 파일 해시를 다시 대조했다. 스칼라 ELF 16개의 측정 구간에서 retire 기록 6,528개의 PC·명령·상대 사이클이 일치했다. 408개 측정 PC 중 403개는 피연산자에 따라 결과가 달랐다. 벡터는 426개 인코딩의 요청과 지연 기록 84,348개가 순서대로 일치했고, 피연산자에 따른 조기 완료를 추가한 모델은 거부됐다. 검사한 설정과 데이터 범위는 [TIMING_CONTRACT](TIMING_CONTRACT.md)에 기록했다.

- [x] production RV64 H/V SoC에서 M/HS/U/VS/VU 각각의 Sscofpmf retire 필터를 검사했다. 모드를 선택한 카운터는 10, 같은 모드를 차단한 카운터는 0만큼 증가했다. 각 ECALL의 PC, cause, MPP/MPV를 확인하고 trace에서 두 결과를 재계산했다. 기존 HS/VS 오버플로 인터럽트 검증과 함께 [HPM_COUNTERS](HPM_COUNTERS.md)에 기록했다.

- [x] Sscofpmf의 M 모드 오버플로를 실제 RV64 H/V SoC에서 확인했다. MIE를 끈 상태에서 OF와 LCOFIP가 설정되고 MIE를 켜면 cause 13으로 진입했다. OF가 설정된 상태의 두 번째 wrap에서는 IRQ가 발생하지 않았고, OF를 지운 뒤 세 번째 wrap에서 다시 cause 13으로 진입했다. 두 IRQ의 저장된 MPP와 tval, MRET 복귀를 검사했다. [HPM_COUNTERS](HPM_COUNTERS.md)

- [x] production RV64 H/V SoC에서 Zawrs의 VS/VU 타임아웃 권한 6개를 확인했다. 예약이 있는 NTO에서 VTW 단독은 cause 22, TW가 설정된 두 조합은 cause 2였다. 각 trap의 PC, 명령 tval, MPP/MPV와 복귀를 확인했다. 예약 없는 NTO는 정상 완료했고, STO 이후 SC.D는 여섯 번 모두 성공했다. 실행과 타임아웃 사이클은 계약 감사에서 다시 대조한다. [Zawrs 규격](https://docs.riscv.org/reference/isa/v20260120/unpriv/zawrs.html)

- [x] 전체 RV64 H/V SoC의 WRS.NTO 대기 중 외부 debug AXI 쓰기를 주입했다. 인접 64바이트 라인의 쓰기 4회에는 예약과 대기가 유지됐고, 예약 라인 내 다른 워드에 32/64비트로 쓴 4회에는 해당 snoop에서 예약이 해제되고 WRS가 완료됐다. 뒤의 SC.W/SC.D는 각각 두 번 실패를 반환했고, 원래 워드와 두 외부 쓰기 값도 검사했다. 코어는 정지시키지 않았다.

- [x] VS의 PMLEN=7 포인터 마스킹을 기존 2단계 주소 변환 테스트에 적용했다. 태그가 붙은 벡터 load/store는 G-stage fault에서 vstart=2로 중단한 뒤 복귀해 완료했다. 벡터 load/store·AMO·CBO의 네 fault에서 stval은 0x400a4000, htval은 0x200a4000을 2비트 우측 이동한 값이었다. PMM=0 대조군은 첫 벡터 store에서 VS page fault와 원래 태그 주소를 기록했다. [포인터 마스킹 규격](https://docs.riscv.org/reference/isa/v20260120/priv/zpm.html)

- [x] RV64 H/V SoC에서 CBO.INVAL/CLEAN/FLUSH/ZERO와 M/HS/U/VS/VU의 envcfg 권한 조합 255개를 확인했다. 정상 완료 128개, cause 2 예외 96개, cause 22 예외 31개였고 예외 PC·명령 tval·MPP/MPV를 검사했다. 허용된 ZERO 17개는 블록 끝에서 5바이트 떨어진 주소를 사용해 정렬된 64바이트 전체만 0으로 만들었다. 모든 케이스에서 양쪽 인접 워드를 보존했고, 세 envcfg에 CBIE 예약값 10을 쓰면 기존 합법값이 유지됐다. [CMO 규격](https://docs.riscv.org/reference/isa/unpriv/cmo.html)

- [x] Svpbmt의 VS/G-stage 3×3 유형 조합과 양쪽 PBMTE 차단을 MMU에서 확인했다. Svnapot은 S-stage와 VS/G-stage 조합 각각에서 64 KiB의 16개 4 KiB 서브페이지를 확인했고, VS/G-stage 예약 인코딩의 fault 종류와 GPA를 대조했다. Svade는 VS·최종 G leaf의 A/D 조건, 암시적 VS PTE 읽기 실패의 GPA, 원래 fetch·load·store에 맞는 예외 코드를 확인했다. MMU 103개가 통과했고 현재 모델·로그를 계약 감사에 연결했다. [Svpbmt 규격](https://docs.riscv.org/reference/isa/v20240411/_attachments/riscv-privileged.pdf) · [Svnapot 규격](https://docs.riscv.org/reference/isa/priv/supervisor.html) · [H 확장 규격](https://docs.riscv.org/reference/isa/priv/hypervisor)

- [x] 수정된 전체 H/V SoC에서 비정렬 HLV.D로 VS/G-stage PBMT 9개 조합을 확인했다. 최종 유형이 IO인 네 경우만 cause 5와 원래 접근 주소를 기록했고, 나머지 다섯 경우는 두 64비트 워드에 걸친 값을 정확히 읽었다. 같은 ELF를 수정 전 모델에서 실행하면 VS=NC/G=IO에서 잘못된 cause 5가 발생했다. 결과는 out/rva23/guest_pbmt_precedence/report.json에 있다.

## 3. 통합 검증과 부팅

- [x] Svpbmt 수정 이전 RTL에서 ACT4 체크인 ELF 663개와 생성 벡터 ELF 2,083개가 모두 통과했다. 공식 핀 0.13.1의 H 미지원으로 참조 모델은 Sail 0.16을 사용했다.
- [x] 후속 upstream ACT4 커밋이 지정한 Sail 0.16으로 H·Sv39x4·PMP ELF 40개를 생성했고 현재 RTL에서 모두 통과했다. `hgatp`, G-stage PTE, VS/VU guest fault, `hstatus.VTVM`, 가상 주소 무효화와 CBO 권한을 확인했다. [ACT4 재현 절차](ACT4_VERIFICATION.md#newer-upstream-act4-sail-pin)
- [x] 같은 upstream 커밋에서 `--certificate RVA23` 필터로 선택한 체크인 ELF 607개가 모두 현재 RTL에서 통과했다. 34개 suite의 선택 목록과 생성 ELF, Sail signature 및 RTL 실행 로그를 감사한다. 생성 벡터 소스는 별도 검증 목록으로 추적한다.
- [x] Svpbmt 수정 이전 1 MiB SoC에서 OpenSBI의 S 모드 진입, DTB 전달, SBI BASE/TIME, supervisor timer interrupt를 확인했다. retire trace에서 두 S ECALL(cause 9)과 S 타이머 인터럽트(cause 5)를 확인했다.
- [x] Linux 6.12 RV64 `Image`를 링크했다. initramfs에 RV64 `/init` ELF와 `/dev/console`, `/dev/kmsg`가 들어 있는 것을 확인했다. 빌드 절차는 `scripts/build_linux_image_msys.sh`에 있다.
- [x] 별도 32 MiB RTL에서 Linux 6.12가 `0x80200000`의 S 모드 첫 명령을 retire한 뒤 U 모드 `/init`을 실행했다. `RV23 LINUX INIT PASS`, `reboot: Power down`, host 종료 코드 0을 확인했다. 21,528,422개 명령 retire, 시뮬레이션 시간 469 ms다. `scripts/audit_linux_boot.py`가 firmware에 내장된 Image 바이트와 RTL·모델·ELF·로그 해시 및 순서대로 나타난 실행 표식을 대조했다. 결과는 `out/linux_bringup/boot_audit.json`에 있다. 기본 production SRAM 1 MiB 구성에서 Linux를 실행했다는 뜻은 아니다.

## 4. 남은 완료 감사

Svpbmt RTL 수정 이전의 ACT4와 Linux 결과는 이전 RTL의 실행 근거다. 수정된 RTL의 재검증 결과가 나오면 현재 소스 기준의 통합 감사에 반영한다.

- [x] Svpbmt 수정 후 production RV64 H/V 모델의 2-issue OoO 테스트를 다시 실행했다. dual issue·execute·retire 각 4회와 younger bypass 6회, 64비트 결과 10개를 현재 모델과 trace에서 재검증했다.
- [x] Svpbmt 수정 후 70단계 기능 회귀와 RV32 릴리스 게이트 6개가 다시 통과했다. 기존 TIM 성능 ELF도 그대로 실행해 비교했다.
- [x] 벡터 실행 엔진에서 네 가지 VTA/VMA 조합으로 `vmsltu.vx`의 128비트 마스크 목적지를 전부 읽어 확인했다. 마스킹과 `vstart`를 적용한 결과 및 `vl=0`과 `vstart=vl`에서 목적지 전체가 보존되는 결과를 확인했다. 비활성 비트와 tail을 보존하는 현 구현의 동작을 검사했다. [V 규격](https://docs.riscv.org/reference/isa/unpriv/v-st-ext)
- [x] 새 마스크 목적지 검사를 포함한 정수 벡터 스트림 825개 패킷을 전체 RV64 H/V 코어에서 통과했다.
- [x] Svpbmt 수정 후 Sail 대조에서 VTA/VMA 66개와 e16/e32/e64 FP 결과·플래그 40개를 다시 확인했다. 허용된 변경 2개와 잘못된 변경 4개의 대조군도 재검증했다.
- [x] 계약 감사에서 현재 RV64 SoC의 RTL·테스트벤치·모델·로그를 대조하고, 정렬된 fetch 16개 위치와 총 464회 동일 라인 쓰기/refill 경합을 확인했다.
- [x] 새 마스크 목적지 검사를 반영한 기능 회귀 70단계와 현재 소스 요구사항 감사를 통과했다.
- [x] 수정된 RTL에서 체크인 ACT4 663개가 모두 통과했다. 현재 RTL·모델 해시, 기존 ELF 663개 해시와 실제 실행 로그를 대조했다.
- [x] 수정된 RTL에서 같은 생성 벡터 ACT4 ELF 2,083개가 모두 통과했다. ADD를 SUB로 바꾼 대조군을 거부했고, 체크인 663개를 포함한 2,746개 전체의 통합 감사를 통과했다.
- [x] 수정된 1 MiB RTL에서 OpenSBI S 모드·DTB·타이머 인계를 재실행했다. 현재 RTL·모델·펌웨어·로그와 S 모드 ECALL 두 건, 타이머 인터럽트 한 건을 대조했다. 시뮬레이터 종료 코드는 0이다.
- [x] 같은 Linux 6.12 Image로 수정된 32 MiB RTL을 부팅했다. S 모드 진입, U 모드 `/init` 실행, `RV23 LINUX INIT PASS`, 전원 종료와 호스트 종료 코드 0을 확인했다. `scripts/audit_linux_boot.py --variant pbmt_fixed --require-isa`가 통과했으며, 실행 근거는 `out/linux_bringup/pbmt_fixed/boot_audit.json`에 있다.
- [x] HS `sie`에 가상 인터럽트 비트를 썼을 때 발생한 잘못된 HS VSEI를 수정했다. 같은 ELF로 수정 전 오동작과 수정 후 HS cause 10 및 VS cause 9 전달을 확인했다. [인터럽트 검증 기록](RVA23_PROFILE_CONTRACT_REVIEW.md#csr-쓰기와-sret-직후-인터럽트)
- [x] HS `sie` 수정 후 RV64 기능 회귀 70단계와 RV32 릴리스 6개 게이트를 통과했다. 종전과 동일한 ACT4 ELF 2,746개도 전부 통과했고, 생성 벡터 ELF 2,083개의 이름과 SHA-256을 이전 실행과 대조했다.
- [x] HS `sie` 수정 후 1 MiB RTL에서 OpenSBI의 S 모드·DTB·타이머 인계를 재검증했다. 별도 32 MiB RTL은 동일 Linux 6.12 Image로 S 모드에 진입하고 U 모드 `/init`을 실행한 뒤 정상 종료했다. 해당 부팅 감사는 `out/linux_bringup/hs_sie_fixed/boot_audit.json`이다.
- [x] 벡터의 혼합 EEW 소스 겹침 수정 후에도 동일 ACT4 ELF 2,746개와 최신 ACT4 H·PMP ELF 40개를 통과했다. Linux를 다시 부팅했고 감사 결과는 `out/linux_bringup/mixed_eew/boot_audit.json`이다.
- [x] indexed segment에서 인덱스가 목적 레지스터와 겹치는 경우와 whole-register 정렬, 레지스터 범위, 예약된 `mew` 및 mask load 인코딩을 점검했다. 추가 6건 모두 cause 2로 트랩했고 `mtval`과 `vstart`를 확인했다.
- [x] 전체 레지스터 이동 네 형식을 `vl=0`과 SEW 8·16·32·64에서 검증했다. 공통 48건은 동일 ELF로 Sail/RTL을 비교했고, `vstart=evl` 및 `vill=1`의 19건은 RTL 결과와 Sail의 예외 동작을 각각 기록했다.
- [x] Zvbb 16개 형식을 합법적인 분수 LMUL 사례 288건 포함 총 471건으로 비교했다. 동일 ELF를 실행한 Sail과 RTL의 이벤트 30,809개가 일치했고 목적지 데이터 3,768개를 독립 예상값과 대조했다.
- [x] VS·VU 및 MPRV+MPV에서 비정렬 접근의 페이지 경계 예외를 검사했다. VS/G-stage 변환 실패 16건과 PMP가 VS/G-stage PTE 읽기를 막은 접근 예외 8건에서 예외 메타데이터가 정확했다. 실패한 접근은 앞쪽 페이지와 load 목적 레지스터를 보존했다. 근거는 `out/rva23/guest_misaligned/report.json`이다.
- [x] Sstvala·Shvstvala의 압축 illegal-instruction 값을 확인했다. 예약된 `C.ADDI4SPN`과 FS=Off의 압축 D 명령 네 가지를 포함한 88개 사례에서 M/HS/VS trap handler가 EPC와 tval을 검증했다. 감사는 176개 trap과 RTL·ELF·trace 해시를 대조한다.
- [x] Sstvecd·Shvstvecd의 Direct 모드에서 Sv39 하위·상위 주소의 12곳에 실제 트랩을 전달했다. 페이지의 마지막 4바이트에서 시작하는 handler를 포함해 첫 실행 PC와 SRET 복귀를 확인했다.
- [x] Bare/Sv39에서 U 모드가 `ECALL`로 HS 테스트 서비스에 `PMLEN=0→7→0`을 요청했다. 여섯 요청의 CSR 설정과 동일 태그 주소의 정상 load/store 4건, 예외 8건이 확인됐다. 같은 ELF에서 U→HS 및 HS→M의 `ECALL`과 RV64I little-endian 바이트 순서를 확인했다.
- [x] Linux 6.14 U 모드의 `prctl` 경로에서도 `PMLEN=0→7→0`과 태그 주소의 스칼라·벡터 메모리 접근을 확인했다. 32 MiB RTL의 부팅 근거는 `out/linux_bringup/supm/boot_audit.json`에 있으며 `--variant supm --require-isa --require-supm`으로 재검사한다.
- [x] VS-stage와 G-stage에서 각각 `VLSEG2E32FF`의 첫 segment fault와 후속 segment의 길이 단축을 확인했다. 마스크를 포함한 8개 사례와 두 번의 같은 PC 재실행이 통과했고, 동일 ELF에서 Sail·RTL 실행 이벤트 2,987개를 대조했다.
- [x] `vl=0`, `vill=1`에서 `VL4RE64`·`VS4R`의 네 레지스터 전송을 확인했다. VS/G 페이지 예외 4건에서 각 EEW의 `vstart`로 복귀했고, 이미 완료된 앞 32바이트는 다시 읽거나 쓰지 않았다. 동일 ELF에서 Sail·RTL 3,467개 이벤트가 일치했다.
- [x] SRAM과 CLINT `MSIP` 사이의 FENCE 여섯 조합을 검증했다. 전체 SoC의 LSU 요청·응답 계측에서 선행 접근 응답이 FENCE retire보다 먼저, 후속 접근 요청이 retire 이후에 발생했다.
- [x] 네 가지 `AMOADD.D` 순서 인코딩과 `LR.D.AQ`·`SC.D.RL`에서 선행 SRAM 쓰기 응답, atomic 요청·응답 및 retire, 후속 SRAM 읽기 요청 순서를 확인했다. SC 성공과 최종 메모리 값도 검사했다.
- [x] 지연된 주소 또는 값을 쓰는 겹침 store 96개와 Sv39 별칭의 페이지 경계 비정렬 store 22개를 확인했다. load 708개가 바이트 기준값과 일치했고, 동일 ELF에서 Sail·RTL 이벤트 10,095개를 대조했다.
- [x] `hgatp` 미지원 MODE 쓰기의 RTL과 테스트 기대값을 바로잡았다. 수정 전 모델이 218번 사례에서 실패한 동일 ELF를 수정 후 전체 SoC에서 통과시켰다. CSR 단위와 279개 CSR geometry 사례가 통과했다.
- [x] HS의 G-stage·VS-stage `HINVAL` 및 VS의 `SINVAL.VMA` 뒤 동일한 두 게스트 주소에서 새 코드를 실행했다. 같은 ELF로 Sail과 수정 후 RTL 이벤트 2,880개를 대조했다.
- [x] `hgatp` 수정 후 production 2-issue OoO 및 캐시 뱅크 검증을 재실행했다. dual issue·execute·retire 각 4회, younger bypass 6회, I/D 동시 뱅크 읽기 104회/2회와 AXI64 SRAM refill 8개를 현재 trace에서 감사했다.
- [x] `hgatp` 수정 후 RV64 기능 회귀 70단계 및 체크인 ACT4 663개, 추가 H·Sv39x4·PMP 40개를 재검증했다.
- [x] `hgatp` 수정 후 생성 벡터 ACT4 2,083개를 동일 ELF로 재검증했다. ADD→SUB 대조군을 거부했고 현재 RTL의 통합 감사에 반영했다.
- [x] `hgatp` 수정 후 RV32 릴리스 게이트 6개와 1 MiB OpenSBI 인계를 재검증했다. 인계는 `scripts/run_opensbi_handoff.py --reuse-probe-firmware`로 보관한 ELF를 그대로 사용했다.
- [x] 32 MiB 벡터 부팅에서 Linux가 V를 `AT_HWCAP`에 노출했다. U 모드 `/init`은 벡터 계산 결과를 검사하고 시스템을 정상 종료했다. `hgatp` 수정 후 `--variant hgatp_vector --reuse-firmware-from vector`로 같은 OpenSBI ELF를 재생했다. `scripts/audit_linux_boot.py --variant hgatp_vector --require-isa`가 커널·DTB 및 내장 `/init`의 U 모드 벡터 명령을 대조했다.
- [x] Sscofpmf의 `scountovf` 읽기를 M·HS·VS에서 `mcounteren`과 `hcounteren`의 48개 조합으로 검증했다. CSR 쓰기로 OF를 설정해도 LCOFIP가 0을 유지하는지, 구현하지 않은 카운터 31의 OF가 0인지 확인했다.
- [x] Sstc의 `stimecmp`·`vstimecmp` 읽기와 쓰기를 다섯 모드 및 M/H의 STCE·TM 비트 조합으로 검증했다. 320개 접근의 읽기 값, 쓰기 후 readback 및 예외 cause·EPC·tval을 확인했다.
- [x] RVV 스칼라 이동 120건의 `vl`·`vstart`·LMUL 경계와 불법 명령 6건의 `vstart` 보존을 같은 ELF로 검증했다. Sail과 RTL의 실행 이벤트 2,915개가 일치했다.
- [x] 전체 H/V SoC에서 RVV 타입·AVL 조합 928건과 설정 전환 13건을 검증했다. `vtype`·`vl`·`vstart`를 확인했고 같은 ELF의 Sail·RTL 실행 이벤트 16,908개가 일치했다.
- [x] M·HS의 HLV.D·HLVX.WU·HSV.D 96건에서 SPVP, VS PTE의 U 비트와 HS/VS SUM을 바꿔 확인했다. 페이지 예외 36건과 허용된 접근 60건을 확인했고 같은 ELF의 Sail·RTL 실행 이벤트 5,801개가 일치했다.
- [x] Bare와 Sv39 주소 별칭의 공유 SRAM 접근 8건에서 스칼라 부분 쓰기·AMO와 벡터 load/store를 교차 실행했다. 뱅크와 캐시 라인 경계에서 최신 데이터 및 인접 워드 보존을 확인했다.
- [x] Sv39에서 스칼라 load, unordered indexed 벡터 load/store, ordered indexed 벡터 store의 Svade A/D 예외 4건을 매핑 복구 후 같은 PC에서 재시도했다. 반복 주소를 쓰는 ordered store는 예외 당시 완료한 원소의 순서, 후속 원소와 스칼라 store의 가시성, 재시작 후 값을 검사했다. 미매핑 페이지의 마스크 사례 두 건도 확인했다. [검증 기록](RVA23_PROFILE_CONTRACT_REVIEW.md#스칼라와-벡터의-공유-sram-접근)
- [x] RVV 고정소수점 곱셈과 좁히기의 반올림·포화 검사 392건을 통과했다. 결과 원소 1,568개와 제외된 원소 및 `vxsat` 보존을 확인했다.
- [x] Sv39·Sv39x4 중간 PTE의 예약 비트 및 G·RSW를 S·VS·G-stage의 네 경로에서 검증했다. 정상 load/store 32건과 예외 112건의 cause·주소를 확인했고 같은 ELF의 Sail·RTL 이벤트 9,997개가 일치했다.
- [x] 128바이트 벡터 store 실행 중 PLIC 인터럽트를 전달했다. 벡터 retire, 인터럽트 진입, 복귀 후 스칼라 store 순서를 trace와 SRAM 쓰기에서 확인했다.
- [x] MRET·SRET 복귀 13건에서 스칼라와 벡터 load가 실제 권한의 Sv39 매핑을 사용했다. M 복귀의 MPRV 유지와 하위 권한 복귀의 해제를 확인했다.
- [x] Svnapot S·VS·G·VS+G 경로에서 64 KiB 내 4 KiB 하위 페이지 16개의 변환과 재매핑을 확인했다. 예약 인코딩 예외 90건, 경계를 넘는 벡터 load와 첫·마지막 하위 페이지의 명령 실행을 검증했다.
- [x] SRAM을 PMA·NC·IO로 동시에 매핑하고 스칼라·벡터 교차 접근 12건을 검증했다. 속성에 맞춰 fence와 비캐시 별칭의 CBO.FLUSH를 실행했고, AXI에서 라인 재충전과 비캐시 읽기를 확인했다.
- [x] Sv39의 PBMT=IO 영역에서 stride 레지스터가 0인 벡터 load/store를 실행했다. AXI가 같은 주소의 벡터 읽기 4개와 마스크로 활성화된 벡터 쓰기 2개를 각각 수락했으며, 최종 값을 스칼라로 확인했다. [RVV 1.0 strided 접근](https://docs.riscv.org/reference/isa/extensions/vector/_attachments/riscv-v-spec.pdf#page=33)
- [x] `CBO.ZERO` 첫 beat와 마지막 beat 사이에 같은 SRAM 라인의 첫 워드를 외부 debug AXI로 썼다. `FENCE RW,RW` 뒤 벡터·스칼라 접근에서 debug 쓰기가 보존됐고, 나머지 일곱 워드는 0, 대상 라인 바로 앞뒤의 워드는 변경되지 않았다.
- [x] 물리 PLIC claim 레지스터의 ordered indexed 벡터 읽기에서 활성 원소 0·2가 ID 3·2를 순서대로 받았고, 마스크된 원소는 초기값을 유지했다. 뒤따르는 스칼라 claim은 ID 4·0을 받았으며 AXI에서 벡터 요청 2건과 스칼라 요청 2건을 확인했다.

- [ ] 위의 `확인 필요` 항목을 규격 조항별로 나눠 실행·예외·상태·순서 검증 근거를 연결한다. 확장 이름 58개 매핑과 ACT 통과를 전체 규격 충족으로 확대 해석하지 않는다.
  - 프로파일 추가 조건의 RTL 근거와 실행 범위는 [RVA23_PROFILE_CONTRACT_REVIEW](RVA23_PROFILE_CONTRACT_REVIEW.md)에 세분했다. 이 표는 기본 ISA/V/H/Ss1p13 전체 조항 감사를 대신하지 않는다.
- [x] 새 DTB의 riscv,isa-base와 riscv,isa-extensions를 사용한 32 MiB RTL 재실행에서 Linux 6.12가 base ISA와 ELF HWCAP을 각각 acdfim으로 보고했다. /init 실행, 정상 종료, host 종료 코드 0을 확인했다. 21,655,063개 명령을 retire했다. scripts/audit_linux_boot.py --variant modern_isa --require-isa로 확인했으며 결과는 out/linux_bringup/modern_isa/boot_audit.json에 있다.

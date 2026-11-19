# RV23 Dual-Issue OoO 작업 정리

2026-11-20: `52e19c4`에서 vector pipeline/shared D-cache 후속 성능 변경을
주 개발 branch에 통합했다. 2/4/8-byte 연속 load grouping과 host Bare
memory-head fast path를 포함한다. 통합된 native 입력 파일은 검증한 고정
worktree 모델과 바이트 단위로 같고 RTL parse/elaboration도 통과했다.
주 폴더의 native H/V 실행과 ACT harness smoke도 갱신 후 통과했다.

확인된 최신 CoreMark 2회는 1,761,562 cycles / IPC 0.313612,
10회는 8,784,522 cycles / IPC 0.314427다. 기존과 동일한 각 ELF다.
최신 RTL의 Linux 6.14 Supm/vector 재실행은 진행 중이다.
이후 소스의 부분 회귀와 [성능 기록](VECTOR_BARE_FASTPATH.md)을 아래 과거의
대규모 ACT·Linux·RV32 release 근거와 구분한다. 전체 RVA23S64 완료 판정은 남아 있다.

아래 광범위 회귀 기록은 2026-11-18의 `802e2e1` 기준이다.
목표는 기존 `core_from_home` RTL을 재사용한 공식 RVA23S64
구현이다. 필수 확장 58개와 RV64I 기본 ISA의 경로는
[구현 맵](../config/rva23_implementation_map.json)에 기록한다. 전체 프로파일
판정은 남은 규격 조항의 실행 근거와 통합 재검증이 필요하다.

## 구현

- RV64 기본 구성의 2-issue OoO frontend, issue queue, ROB, LSQ와 2개 retire 경로.
- I/D L1 각 32 KiB. 각각 64비트 뱅크 2개로 128비트 명령 페치와 서로 다른
  뱅크에 대한 동시 데이터 읽기를 지원한다. 메인 버스는 AXI64, 공유 SRAM은 1 MiB다.
- CLINT, PLIC, halt/drain/resume, debug AXI와 retire trace를 연결했다.
- S/HS/VS/VU, Sv39 및 Sv39x4, 가상 인터럽트, RVV VLEN128/ELEN64,
  스칼라 F/D와 벡터 실행·메모리 경로를 통합했다. 최근 변경은 미지원
  `hgatp.MODE` 쓰기에서도 정렬된 새 루트 PPN을 반영하는 처리다.
- RV32 회귀 구성과 변경 전 [RV32 기준 소스](../baselines/rv32_verified_20261029/README.md)를 보존한다.

## 검증 기록

2026-11-18에 후속 upstream ACT4의 Sail 0.16 조합에서 RVA23 필터의
체크인 ELF 607개와 별도 H·Sv39x4·PMP ELF 40개가 모두 통과했다.
새 목록의 생성·실행 근거는 `out/act4/current_rva23_inventory/`,
`out/act4/current_h_extended/`에 있다. [재현 및 감사](ACT4_VERIFICATION.md)

후속 upstream 생성 벡터 2,301개도 Sail 기대값과 self-checking ELF
생성을 마쳤고 현재 RTL에서 모두 통과했다. `audit_act4_current_vector.py`가
선택 목록·생성 소스·signature·ELF·RTL/model·실행 로그 해시와 실제 PASS
witness를 검사했다. 근거는 `out/act4/current_vector/execution_audit.json`이며
통합 요구사항 감사에도 포함한다. 전체 규격 조항 검토와 공식 인증은 별도다.

| 검사 | 확인한 결과 |
|---|---|
| `hgatp` 수정 검증 | 같은 ELF가 수정 전 218번 CSR 사례에서 실패했고 수정 후 279개 CSR 사례를 통과했다. 게스트 명령어 매핑 갱신은 Sail과 수정 후 RTL에서 실행 이벤트 2,880개가 일치했다. |
| RV64 기능 회귀 | `hgatp` 수정 후 70단계 통과. |
| RV32 회귀 | `hgatp` 수정 후 릴리스 게이트 6개 통과. |
| OoO와 뱅크 | `hgatp` 수정 후 dual issue·execute·retire 각각 4회, 후속 독립 명령 선행 실행 6회, I/D 뱅크 동시 읽기 104회/2회를 다시 관찰했다. SRAM 라인 재충전은 AXI 64비트 읽기 8회였다. |
| 벡터 레지스터 그룹·인코딩 | 전체 SoC에서 허용 동작 5개와 불법 명령 예외 20개. 혼합 EEW와 예약 메모리 인코딩의 동일 ELF Sail/RTL 비교에서 예외 13개를 포함한 이벤트 351개 일치 |
| 벡터 상태·FP | 현재 RTL에서 Sail과 22개 SEW/LMUL 설정의 벡터 상태, 66개 agnostic 정책 사례, FP 결과·플래그 40개를 대조했다. 스칼라 이동 120건과 예외 6건을 추가했다. |
| 벡터 설정 | 타입·AVL 조합 928건과 설정 전환 13건을 실행했다. `vl` 유지, `vill`과 정상 설정 복구를 확인했고 같은 ELF의 Sail·RTL 이벤트 16,908개가 일치했다. |
| OpenSBI | 기본 1 MiB 구성에서 보관한 ELF로 S 모드 인계, SBI BASE/TIME 및 supervisor 타이머 인터럽트를 재검증했다. |
| Linux 6.12 | 같은 OpenSBI ELF·커널 Image·DTB를 사용한 32 MiB 시뮬레이션에서 `hgatp` 수정 전후에 각각 21,822,717개 명령을 retire했다. 수정 후 부팅 감사가 S 모드 진입, U 모드 `/init`의 벡터 계산 및 정상 종료를 확인했다. |
| ACT4 | `hgatp` 수정 후 고정 체크인 ELF 663개와 생성 벡터 ELF 2,083개가 통과했다. 추가 H·Sv39x4·PMP ELF 40개도 통과했다. 현재 RTL 통합 감사에 결과를 반영했다. [ACT4 절차와 Sail 버전 차이](ACT4_VERIFICATION.md) |
| 게스트 비정렬 접근 | VS·VU와 MPRV+MPV 경로에서 32비트 load/store를 검증했다. 페이지 변환 예외 16건과 PMP가 PTE 읽기를 차단한 접근 예외 8건의 메타데이터가 정확했고 메모리와 목적 레지스터가 보존됐다. |

Linux 6.14의 사용자 포인터 마스킹(Supm) 검증도 32 MiB RTL에서 통과했다.
`/init`이 `prctl`로 `PMLEN=0→7→0`을 설정하고 각 설정을 읽어 확인했다.
마스킹을 켠 상태에서 태그 주소로 스칼라·벡터 읽기/쓰기를 실행했고,
태그가 없는 주소에서 벡터 결과 24와 28을 확인했다. 22,423,386개 명령을
retire하고 전원을 껐다. [콘솔 발췌](evidence/linux-supm-boot-2026-11-17.txt)

제작 단계에서 사용한 빌드 파일, 전체 trace, Linux Image와 ACT4 ELF는
각 실행의 `out/`에 생성된다. upstream 소스는 고정 커밋의 Git submodule로 받는다.
검증 실행 명령과 범위는 [README](../README.md),
[규격 조항 검토](RVA23_PROFILE_CONTRACT_REVIEW.md)에 있다.

## 동일 CoreMark ELF 비교

| 구성 | 명령 수 | 사이클 | IPC |
|---|---:|---:|---:|
| 기존 TIM 기록 | 576,450 | 437,950 | 1.316246 |
| 현재 캐시 구성의 RV32 호환 모드 | 576,450 | 513,076 | 1.123518 |

비교에 쓴 [보존 ELF](../sw/benchmarks/coremark/fixtures/tim_reference.elf)의
SHA-256은 `33fe48d15f11a4a396d821fa1feecac527e8322a6af61b8797debb2f02af69ac`다.
이 수치는 두 RV32 메모리 구성에서 같은 프로그램을 비교한 기록이다.
[캐시 사이클 분석](CACHE_CYCLE_ANALYSIS.md)

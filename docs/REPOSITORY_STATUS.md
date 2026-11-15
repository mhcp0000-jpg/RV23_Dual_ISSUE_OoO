# RV23 Dual-Issue OoO 작업 정리

2026-11-16 기준. 목표는 기존 `core_from_home` RTL을 재사용한 공식 RVA23S64
구현이다. 필수 확장 58개와 RV64I 기본 ISA의 경로는
[구현 맵](../config/rva23_implementation_map.json)에 기록한다. 전체 프로파일
판정은 남은 규격 조항의 실행 근거와 통합 재검증이 필요하다.

## 구현

- RV64 기본 구성의 2-issue OoO frontend, issue queue, ROB, LSQ와 2개 retire 경로.
- I/D L1 각 32 KiB. 각각 64비트 뱅크 2개로 128비트 명령 페치와 서로 다른
  뱅크에 대한 동시 데이터 읽기를 지원한다. 메인 버스는 AXI64, 공유 SRAM은 1 MiB다.
- CLINT, PLIC, halt/drain/resume, debug AXI와 retire trace를 연결했다.
- S/HS/VS/VU, Sv39 및 Sv39x4, 가상 인터럽트, RVV VLEN128/ELEN64,
  스칼라 F/D와 벡터 실행·메모리 경로를 통합했다. 최근 변경은 혼합 EEW로
  읽는 벡터 소스가 겹칠 때 예약 인코딩을 거부하는 처리다.
- RV32 회귀 구성과 변경 전 [RV32 기준 소스](../baselines/rv32_verified_20261029/README.md)를 보존한다.

## 검증 기록

| 검사 | 확인한 결과 |
|---|---|
| RV64 기능 회귀 | 현재 RTL에서 70단계 통과 |
| RV32 회귀 | 6개 릴리스 게이트 통과 |
| OoO와 뱅크 | dual issue·execute·retire 각각 4회, 후속 독립 명령 선행 실행 6회, I/D 뱅크 동시 읽기 104회/2회 |
| 혼합 EEW | 전체 SoC에서 허용 동작 5개와 불법 명령 예외 14개. 혼합 EEW 사례의 동일 ELF Sail/RTL 비교에서 208개 이벤트 일치 |
| Linux 6.12 | 32 MiB 데모 구성에서 S 모드 진입, U 모드 `/init` 실행, SBI 전원 종료. [콘솔 발췌](evidence/linux-boot-2026-11-16.txt) |
| ACT4 | 이전 RTL에서 선택한 2,746개 전부 통과. 현재 RTL에서는 같은 ELF로 체크인 663개 통과, 생성 벡터 2,083개 재실행 중. [ACT4 절차와 Sail 버전 차이](ACT4_VERIFICATION.md) |

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

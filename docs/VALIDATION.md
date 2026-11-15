# RV32 검증 결과 — 2026-10-29

현재 목표는 **RV32IMFC_Zicsr_Zifencei / ilp32f, M/U 모드**다. 기본 XLEN32,
I/D 각 32 KiB, 64-byte line, main AXI4와 공용 SRAM 1 MiB를 사용한다.
물리 메모리/버스 data beat는 64 bit이며 CPU XLEN32와 구분한다.
폴더와 rv23_ 모듈 이름은 유지한다. 이전 RV64 결과는
[역사 문서](VALIDATION_20261028_RV64.md)에 분리했다.

| 검증 | 실제 결과 | 확인 범위 |
|---|---|---|
| pyslang elaboration | PASS, 오류 0 | RTL 51개, RV32 기본/64-bit 보조 elaboration. diagnostic 350개는 로그에 보존 |
| 기존/추가 block·backend | **58/58 PASS** | rename/ROB/IQ/LSU/연산기/frontend/CSR/PMP/AXI/PLIC/CLINT 및 unit geometry 변형 |
| RV32F exact oracle | **113,600 × 정적/동적 각각 PASS** | exact-rational 예상 result/fflags, 다섯 RM; 틀린 예상값의 실패 검출 포함 |
| RV32 소프트웨어 | **22/22 검증 PASS** | C/FP, RV32/RV32C/M-U, CSR/PMP, precise fault, LSU pressure, HTIF, 보관 arithmetic 입력, CoreMark |
| cache/SRAM 기본 | **97 checks PASS** | I128/D64 1-cycle hit, dual bank/동일 bank 중재, 연속 fetch, snoop/refill/FENCE.I/held-response 경합, word 단위 진행 |
| cache fault/capacity | **4,648 checks PASS** | 512 lines × 8 words 전체 32 KiB, error/부분 refill, final beat, snoop/refill bank-write 충돌 |
| random system scoreboard | **3 seeds × 1,024 transactions PASS** | 각 seed에서 2,048 words 초기화 후 CPU0/CPU1/debug의 size/byte mask와 I/D 관측값 비교 |
| AXI 주소 경합 | PASS + 수정 전 RTL 실패 재현 | AR/AW stall 중 master/ID/payload 유지, 이후 handshake 소유권 |
| ROB sequence 소진 | PASS + 수정 전 RTL 실패 재현 | 실제 ROB48/SEQ8, 3 epochs/1 wrap/66 redirects/388 dispatches, checkpoint-resident invariant |
| 최종 입력/결과 감사 | **PASS** | 전체 gate의 현재 RTL/TB/ELF/실행파일/로그 hash와 기대 case 집합 확인 |

소프트웨어 22개에는 **의도적으로 잘못된 예상값을 넣은 3개 negative control**이 포함된다.
이들은 기대한 오류 메시지와 nonzero 종료를 확인했을 때만 검증 PASS다. PMP 권한 변경
4개는 의도한 접근 거부 handler의 HTIF code 1과 정확한 fault 주소를 확인한다.
이를 모든 payload의 정상 exit(0)으로 표현하지 않는다.

## 추가된 end-to-end 확인

`rv32_system_contract.S`는 실제 core에서 MXL32를 읽고, RV64 전용 LD/SD/ADDIW 세 명령이
illegal-instruction trap을 내는지 확인한다. 이어 자기수정 코드의 `a0=1 → 42`와
FENCE.I retire, 실제 MSIP/MTIP/MEIP handler·PLIC claim/complete, native halt 동안의
AXI 메모리 read/write와 실제 retire 재개를 확인했다. RV32F FCVT ELF는 static/dynamic
rounding을 포함한 **14,448 conversions**를 self-check했다.

cache random seeds는 `1`, `305419896`, `3735928559`다. 한 번의 좋은 seed나 단순한
컴파일 성공을 전체 동작 검증으로 대신하지 않았다. 보관된 arithmetic assembly는
재실행했으며 새 RISC-V DV/UVM 장기 생성을 수행했다고 주장하지 않는다.

## 찾아서 수정한 문제

- main AXI crossbar가 stalled 주소의 소유자를 새 요청으로 바꾸던 문제: AR/AW owner lock.
  수정 전 사본은 같은 전용 TB에서 실패한다. assertion을 끄지 않았다.
- 재사용 host DPI가 posedge callback에서 AXI 주소를 구동하던 경합: AR/AW 구동을
  negedge에 시작하도록 수정했다. 실제 HTIF 문자열/proxy/종료 테스트로 다시 확인했다.
- ROB entry 여유가 있어도 signed modulo sequence 예산이 부족할 수 있다. backend가
  ROB allocation 거절을 미리 반영하지 못하던 문제를 독립적인 prospective sequence
  credit로 수정했다. `dispatch_fire → rob_alloc_ready` assertion도 추가했다.
  수정 전에는 count=22/span=127/requested=2에서 실패하고, 수정 후에는 소진·복구·wrap이 통과한다.
- 예전 FP smoke의 FS 초기화 누락과 `#ifdef` negative flag를 값 0으로 정의하던 빌드 오류를
  수정했다. positive와 negative payload를 별도로 다시 컴파일하고 실행했다.
- 직렬 IF adapter/LSU arbiter를 두-bank hit 경로로 바꿨다. I128/D64 hit는 1 cycle이며
  서로 다른 bank의 두 LSU read는 함께 처리한다. 같은 word 쓰기의 응답만 기다리며
  같은 line의 다른 word를 불필요하게 차단하지 않는다. 이전 넓은 lock의 실패도 재현했다.
- SRAM 쓰기는 I-cache의 해당 line을 무효화하고 D-cache의 resident word에는 실제
  data/byte strobe를 merge한다. write miss는 allocate하지 않는다. refill 중 해당
  line 쓰기/FENCE.I는 설치를 취소하고, snoop/refill bank-write 충돌은 backpressure로 처리한다.

## CoreMark — bank 처리량 복구

main AXI는 64 bit이고 각 L1은 64-bit 2-bank, 총 32 KiB다. I128/D64 hit는 1 cycle,
서로 다른 bank의 두 LSU hit는 동시에 처리한다. D-cache는 write-through/no-write-allocate를
유지하며 실제 SRAM write snoop의 byte strobe를 resident word에 merge한다.

upstream commit `1f483d5b8316753a742cbf5590caf5bd0a4e4777`, GCC 15.2 `-O2`,
RV32IMFC/ilp32f. 같은 ELF의 전후 결과이며 CRC `e9f5/e714/1fd7/8e3a`가 일치했다.

| Iter | 수정 전 cycles | 수정 후 cycles | 수정 전 IPC | 수정 후 IPC | cycle 기준 배속 |
|---|---:|---:|---:|---:|---:|
| 2 | 2,617,843 | 528,008 | 0.221349 | 1.097442 | 4.958× |
| 10 | 13,060,634 | 2,618,266 | 0.221816 | 1.106480 | 4.988× |

## Write-through 경로 추가 수정

두-bank 적용 직후의 IPC와 별도로, 이번에는 cache engine의 요청 저장→SEND 대기와
bridge의 registered 응답→cache 응답 저장 대기를 줄였다. 빈 engine은 수락 cycle에
요청을 내보내며, downstream이 막히면 같은 payload를 저장해 유지한다. write/uncached
read는 실제 bridge 응답을 바로 전달하고 CPU가 받지 않으면 포트별 holding slot에
저장한다. refill 완료는 기존 registered 경로를 유지한다. store 완료는 bus 응답 뒤다.

동일한 시스템 probe의 SRAM store는 **8 → 6 cycles**,
CLINT read는 **7 → 5 cycles**다. I/D hit는 여전히 1 cycle이다.
아래는 직전 banked 구현과 동일 ELF를 비교한 추가 개선분이다.

| Iter | 직전 banked cycles | 현재 cycles | 직전 IPC | 현재 IPC | cycle 감소 |
|---|---:|---:|---:|---:|---:|
| 2 | 547,601 | 528,008 | 1.058176 | 1.097442 | 3.58% |
| 10 | 2,718,722 | 2,618,266 | 1.065596 | 1.106480 | 3.69% |

직전 RTL/native binary/ELF/log는 `out/performance/wt_before/`에 별도로 보존했다.
`out/performance/write_path/report.json`은 그 결과와 현재 결과의 hash를 묶는다.
요청 수락 edge, stall 중 ID/주소/크기/privilege/ROB seq/data/strobe 보존, 버스 응답 전
완료 금지, ready CPU의 단일 완료, held response, 다른 LSU로의 owner 전환을 검사했다.
보존한 이전 RTL은 새 acceptance-edge 검사에서 실패하는 것도 확인했다.



## 과거 TIM과 같은 ELF로 비교한 정정 결과

기존 CoreMark runner는 `rv32imc/ilp32`, function/data sections 및 linker GC를 사용했다.
새 회귀 runner에는 `rv32imfc/ilp32f`, `--no-relax` 공통 옵션을 적용했다. source/startup/
linker script가 같아도 실행 코드와 배치가 달라졌다. 캐시로 바꾼다는 이유로 ELF를
바꿀 필요는 없었으며, 과거 TIM 대비 비교 조건을 통제하지 못한 것이다.

과거 IPC 1.316246의 release 기록과 SHA-256이 같은 ELF를 찾아 재컴파일 없이
현재 cached SoC에서 실행했다. ELF SHA-256은 `33fe48d15f11a4a396d821fa1feecac527e8322a6af61b8797debb2f02af69ac`이다.

| 구성 | cycles | timed instructions | IPC |
|---|---:|---:|---:|
| 과거 TIM 기록 | 437,950 | 576,450 | 1.316246 |
| 현재 cache, 위와 동일 ELF | 513,076 | 576,450 | 1.123518 |

CRC/exit도 통과했다. 이 표의 TIM 값은 보존된 과거 실행 기록이며 TIM을 새로
실행한 결과는 아니다. 동일 ELF로 맞췄지만 RTL 구성 차이의 원인별 cycle 분해를
완료한 것은 아니다. 위의 2/10회 cache A/B 표는 각 행 내부에서 같은 ELF를 사용한
유효한 비교이며, 그 IPC를 과거 TIM과 직접 비교하면 안 된다.
고정 ELF/과거 release 사본/현재 native log와 입력 hash는
`out/performance/tim_reference_elf/report.json`에 보존했다. 이후 TIM 대비 성능
판단에는 이 보존 ELF를 사용하며 재빌드한 파일로 조용히 교체하지 않는다.



2회 timed instructions 579,458, 10회 2,897,058으로
각 전후가 동일했다. 579,454개 명령의 timed-body retire control metadata도
같았다. 명령별 `mcycle` 파생 값은 달라지므로 전체 데이터 동등성으로 표현하지 않는다.

기존 TIM의 IPC 1.316246은 별도 메모리 경로의 기록이며 현재 달성값이 아니다.
TIM과 비교할 때는 위 정정 표의 보존 ELF 결과를 사용한다.
현재도 AXI write-through 응답 대기와 single-beat refill은 남아 있다. 10회까지의
반복 추세 확인이며 warm-only 구간/공식 CoreMark score 또는 STA sign-off가 아니다.

9-cycle IF hit와 4-cycle D hit가 생긴 원인, 수정 전후의 commit 공백, 실제 bank 구조와
남은 한계는 [CACHE_CYCLE_ANALYSIS](CACHE_CYCLE_ANALYSIS.md)에 정리했다.
이전 전체 무효화/주소별 무효화 단계의 `out/performance/comparison.json`과
`out/performance/iterations/`는 보존한 과거 결과이며 현재 측정으로 취급하지 않는다.

## 재현과 증거

```powershell
python scripts/run_all_rv32_checks.py
python scripts/audit_rv32_release.py
python scripts/compare_banked_performance.py
python scripts/check_banked_control_trace.py
python scripts/save_verification_snapshot.py
```

전체 구성 스크립트의 각 검증 단계와 최종 감사는 실제로 실행했다. 개별 runner는
`run_regression.py --resume`, `run_programs.py --resume`, `run_extended.py`,
`run_bus_lock_checks.py`, `run_sequence_negative.py`다. resume은 같은 입력/실행파일
hash의 결과에만 사용한다. RTL을 변경한 경우 검토 후 `check_manifest.py --update`로
provenance를 갱신하고 관련 검증을 재실행한다. one-time import helper는 기존 검증
입력을 덮어쓰지 못하도록 잠갔다.

보존 snapshot은 [verification_snapshot.json](verification_snapshot.json), 현재 원시
보고서는 `out/rv32_release_audit.json`, `out/regression/report.json`,
`out/programs/report.json`, `out/extended.json`이다. 시뮬레이션은 Verilator 5.050,
assertion 활성화로 수행했다. 원본 My_core RTL은 수정하지 않았다.

전체 ISA 인증/장기 Spike·Sail differential, IEEE 4-state 보편 증명, Linux/MMU/S-mode,
A/D/V 확장, 표준 JTAG Debug Module, CDC/물리 SRAM macro·STA sign-off는 수행 범위에
포함하지 않는다. 해당 기능이나 sign-off가 완료됐다는 주장은 하지 않는다.

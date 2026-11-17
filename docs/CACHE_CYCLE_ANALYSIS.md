# Cache cycle 분석과 수정 — 검증 갱신 2026-11-17T13:24:43+09:00

기존 코어의 연산 블록 대부분을 재사용했지만, 처음 통합할 때 메모리 경로의 처리량을
보존하지 못했다. main AXI는 원본도 현재도 64 bit다. 기존 TIM 내부 128-bit 병렬 읽기를
64-bit 순차 읽기로 대체한 것이므로, main bus 폭을 64 bit로 둔 것 자체가 하락 원인은 아니다.

## 실제로 늦어진 경로

| 항목 | 직렬 캐시 구현 | 현재 구현 |
|---|---|---|
| 128-bit instruction hit | 64-bit 두 번을 순서대로 처리, **9 cycles** | 64-bit 두 bank 동시 읽기, **1 cycle** |
| 64-bit data hit | arbiter + LOOKUP/CHECK/RESP, **4 cycles** | 직접 bank 동기 읽기, **1 cycle** |
| 서로 다른 bank의 두 read | 첫 응답이 끝날 때까지 다른 요청 수락 지연 | 같은 cycle 수락/응답 |
| 같은 bank의 두 read | 전체 transaction 직렬화 | read port만 한 cycle씩 round-robin |
| write hit | 해당 line을 버리고 이후 load가 refill | 실제 SRAM 쓰기 수락의 data/strobe를 resident word에 merge |
| 진행 중인 write와 다른 word | 같은 64B line 전체를 응답까지 차단 | 같은 8B word만 차단 |

`rv23_cache`는 512개의 shared tag/valid와 bank당 2,048 × 64-bit data를 가진다.
두 bank 합계가 32 KiB이며 I/D에 각각 하나씩 있다. bank bit는 address[3]이고,
정렬된 16B fetch는 항상 두 bank를 함께 읽는다. 두 LSU는 bank가 다르면 함께 처리한다.
bank당 1R1W이며, main SRAM 1 MiB로 향하는 외부 경로는 AXI64 그대로다. TIM 우회 경로를
추가한 것이 아니다. 각 캐시의 miss/write-through engine은 하나이며 다른 resident
word의 hit는 진행할 수 있다. store 성공 응답은 여전히 외부 버스 응답을 기다린다.

latency 단위는 수락 edge에서 첫 registered response까지의 clock 수다. canonical
memory TB는 1-cycle hit, 128-bit 연속 fetch, bank 충돌·응답 backpressure·쓰기 중 다른
word 진행을 assert한다. `profile_memory_paths.py --label before/after`의 독립 로그도 남겼다.

## 같은 ELF로 비교

| Iter | 수정 전 cycles | 수정 후 cycles | 수정 전 IPC | 수정 후 IPC | cycle 기준 배속 |
|---|---:|---:|---:|---:|---:|
| 2 | 2,617,843 | 528,008 | 0.221349 | 1.097442 | 4.958× |
| 10 | 13,060,634 | 2,618,266 | 0.221816 | 1.106480 | 4.988× |

각 행은 동일 ELF 바이트를 보존한 수정 전/후 실행파일에 넣어 비교했다. 2회는
579,458명령, 10회는 2,897,058명령으로 전후가 같고
seed/list/matrix/state CRC도 일치한다. 두 회수 모두 reset/cold start에서 시작한다.
별도로 warm-only 창을 분리한 측정은 아니며 10회까지의 반복 추세를 확인한 것이다.

전체 ELF 적재 후 계측에서 D-cache miss는 2회 19,914 →
64, 10회 98,083 →
64로 줄었다. 이 범위는 CSR timed 창보다 넓다.

## 심한 cycle 공백의 위치

`start_time` 진입부터 `stop_time` 진입까지 retire cycle group을 비교했다.
CSR 측정과 bookend가 다르므로 위 timed cycles와 구분한다.

| 지표 | 수정 전 | 수정 후 |
|---|---:|---:|
| 창의 cycle 수 | 2,617,893 | 528,045 |
| commit 없는 cycle 수 | 2,229,132 | 175,328 |
| 두 명령 commit cycle 수 | 190,693 | 226,737 |

수정 전 가장 큰 공백 집계는 `core_bench_list+0x42`, PC `0x800007d4`의
`lw a4,0(s0)` 앞이다. 이어지는 `sw a3,0(s0)`와 다음 노드 추적이 반복된다.
쓰기마다 cache line을 버리던 동작은 이 load/store 반복에서 특히 불리했다.
PC별 공백은 **다음 retire 묶음의 첫 PC에 배정한 간접 지표**이며, 그 명령 하나의
실행 지연이나 특정 원인의 stall cycle이라고 단정하지 않는다.

같은 창의 **579,454개 명령**은 retire 순서·PC·opcode·목적지·trap·CSR
metadata가 전후 동일했다. `mcycle`에서 파생되는 operand 값은 비교에서 제외했다.
이는 전체 ISA/데이터 동등성 증명이 아니다.

## 동작과 보존 조건 검증

- 시스템 TB: 97 checks. 연속 128-bit fetch, dual bank, same-bank
  중재, 같은 line의 다른 word 진행, resident byte snoop, 실제 SRAM/PLIC/CLINT/debug.
- cache TB: 4,648 checks. 512 lines × 8 words = 4,096 words의
  전체 32 KiB hit, 오류/부분 refill, final-beat invalidate, snoop/refill bank-write 충돌.
- 마지막 I-refill의 FENCE.I, code write와 refill, stalled 128-bit 응답의 안정성.
- 넓은 line lock의 이전 RTL은 새 progress 검사에서 실제 실패한다.
- 기존 58 block/backend, 22 RV32 ELF, 3 seeded memory scoreboard와 최종 6-gate audit.

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

## 남은 성능 차이

이전 TIM의 IPC 1.316246은 별도 메모리 경로의 기록이다. cache A/B 표의 ELF와
달랐으며, 위 정정 표에 과거와 같은 ELF의 현재 측정을 분리했다. write-through 전송/응답은 main AXI에서 직렬 처리하며,
refill도 여전히 8개의 single-beat 전송이다. cache hit bandwidth와 외부 쓰기 처리량을
구분해야 한다. `PATH_PERF`의 engine busy cycle은 계산과 겹칠 수 있으므로 전부를
추가 stall로 합산하지 않는다. write combining/burst/write-back은 별도 설계·검증 항목이다.
새 주파수/STA 결과는 없으며 이 문서의 배속은 동일 clock의 cycle 수 비교다.

## 증거와 재현

`out/performance/banked_before/`에 직렬 구현 RTL/TB/native binary/2회·10회 ELF·로그를
보존했다. `out/performance/banked_after/report.json`은 전후 binary/source/ELF/log와
2회 retire CSV hash를 묶는다. `banked_stage1/`은 두-bank 적용 후 word-lock 보정 전의
중간 결과다. 이 중간 수치를 현재 결과로 취급하지 않는다.

```powershell
python scripts/run_all_rv32_checks.py
python scripts/profile_memory_paths.py --label after
python scripts/save_verification_snapshot.py
```

전체 runner는 입력/실행파일/hash가 같은 결과만 재사용한다. 기준 native binary/ELF
사본은 이 프로젝트의 보존 산출물이며 원본 My_core의 실행/합성 작업을 재개하지 않는다.

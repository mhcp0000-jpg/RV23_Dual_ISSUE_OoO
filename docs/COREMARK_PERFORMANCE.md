# CoreMark 성능과 개선 후보

현재 RV64 H/V SoC에서 같은 upstream 소스·LP64D ABI·메모리 구성으로
O2 스칼라, O3 스칼라, O3 자동 벡터화를 측정한다. 기존 RV32 측정과
새 RV64 측정은 서로 다른 ELF이므로 별도 표로 다룬다.

이 결과는 짧은 RTL 실행의 CoreMark/MHz 추정치다. EEMBC의 최소 실행
시간과 검증 절차를 완료한 공식 점수가 아니다.
[공식 실행·보고 규칙](https://github.com/eembc/coremark/blob/1f483d5b8316753a742cbf5590caf5bd0a4e4777/README.md)

## 측정 조건

- upstream commit: `1f483d5b8316753a742cbf5590caf5bd0a4e4777`, 알고리즘 소스 변경 없음.
- 현재 production RTL, RV64 H/V, VLEN128/ELEN64, I/D 각각 32 KiB,
  캐시당 64비트 뱅크 두 개, AXI64, 1 MiB SRAM.
- GCC 15.2, `-march=rv64gcv_zba_zbb_zbs_zicond -mabi=lp64d`, static 2,000-byte data,
  performance seeds `0,0,0x66`, 한 hart, 각 실행은 reset/cold start.
- O2/O3 스칼라는 `-fno-tree-vectorize`, RVV는 O3와
  `-ftree-vectorize -fvect-cost-model=dynamic -mrvv-vector-bits=zvl`.
- 모든 번역 단위에 같은 variant 옵션을 사용한다. 전체 인자와 각 ELF의
  SHA-256은 실행 보고서에 기록한다. variant·iteration 변경으로 생긴 ELF 차이를 명시한다.
- RV64 전용 port는 64비트 pointer/size, 8바이트 정렬과 단일 CSR 읽기를 사용한다.
  기존 RV32 port와 고정 ELF는 보존한다.
- `cycles = Δmcycle`, `instructions = Δminstret`, `IPC = instructions/cycles`,
  `CoreMark/MHz estimate = iterations × 1,000,000 / cycles`.
  실제 합성 clock 또는 CoreMark/sec를 측정한 것은 아니다.

## RV64 10회 주측정

각 실행은 reset/cold start이며 동일 작업을 10회 반복해 초기 cache·predictor
영향을 줄인다. warm-only 구간만 따로 측정한 값은 아니다. 세 빌드의
10회 비교와 CRC·입력·모델·ELF·로그 해시 감사가 모두 완료됐다.

| Build | Iterations | Cycles | Instructions | IPC | CoreMark/MHz 추정 |
|---|---:|---:|---:|---:|---:|
| O2 scalar, 완료 | 10 | 4,896,919 | 2,997,696 | 0.612160 | 2.042100 |
| O3 scalar, 완료 | 10 | 4,902,692 | 3,036,405 | 0.619334 | 2.039696 |
| O3 auto-RVV, 완료 | 10 | 11,396,161 | 2,762,088 | 0.242370 | 0.877488 |

[여섯 실행의 입력·CRC·로그 감사](evidence/coremark_rv64.json)는
`complete_benchmark_plan=true`다. 이는 측정 계획 완료이며 공식 CoreMark 인증이나
전체 RVA23S64 검증 완료를 뜻하지 않는다. 이전 다섯 실행 시점의 진행 근거는
`coremark_rv64_progress.json`에 별도로 보존한다. O2는 2회와 10회 모두 I-cache
miss 138회·D-cache miss 75회, D read engine busy 4,449 cycles였다.
cycles/iteration은 491,953.5에서 489,691.9로 약 0.46% 감소했다.
cache miss 카운터와 engine busy는 전체 프로그램 범위라 timed stall
분해로 해석하지 않는다. RVV 10회는 O3 scalar의 약 2.324배 cycles를 사용했다.
O3 scalar는 O2보다 IPC가 높지만 명령 수와 cycles도 더 많아 CoreMark/MHz는
조금 낮았다. 서로 다른 compiler build의 IPC 상승을 그대로 점수 향상으로 보지 않는다.

## RV64 2회 예비 비교

세 빌드의 2회 비교는 완료됐다. 각 행의 seed/list/matrix/state CRC는
`e9f5/e714/1fd7/8e3a`이며 같은 iteration의 final CRC도 일치했다.
10회 확장 결과는 위 표와 전체 측정 근거에 있다. 아래는 별도로 보존한 예비 비교다.

| Build | Iterations | Cycles | Instructions | IPC | CoreMark/MHz 추정 | Static V |
|---|---:|---:|---:|---:|---:|---:|
| O2 scalar | 2 | 983,907 | 599,574 | 0.609381 | 2.032712 | 0 |
| O3 scalar | 2 | 985,200 | 607,308 | 0.616431 | 2.030045 | 0 |
| O3 auto-RVV | 2 | 2,284,058 | 552,447 | 0.241871 | 0.875635 | 316 |

[입력·모델·ELF·로그 해시에 묶인 측정 근거](evidence/coremark_rv64_short.json).
GCC 진단과 disassembly에서 벡터화가 확인됐고, retire profile에서도 V 설정
25,665개·연산 60,153개·load 8,432개·store 257개가 실행됐다.
RVV의 cycles는 O3 scalar의 약 2.318배였다. 이 컴파일/현재 RTL 조합에서는
자동 벡터화로 CoreMark가 빨라지지 않았다. 명령 수가 줄어도 현재 벡터
원소 실행·별도 메모리 경로·명령 직렬화의 비용을 함께 봐야 한다.

O2 실행 전체의 D-cache hit/miss는 109,550/75이고, D read engine busy는
4,449 cycles, write engine busy는 192,001 cycles였다. 이 값은 초기화와
출력을 포함하므로 timed cycles와 직접 빼서 stall 원인별 합계를 만들지 않는다.
벡터 원소의 별도 메모리 경로는 D-cache 카운터에 모두 포함되지 않는다.
O2의 retire 공백은 `core_state_transition` 155,358, `core_bench_list` 130,074
cycles에 배정됐다. O3 scalar의 `matrix_test` 공백 157,952에 비해 RVV에서는
1,480,982였다. 이는 다음 retire PC에 배정한 간접 집계이며 인과적 stall 분해가 아니다.
이번 세 timed profile에서 스칼라 DIV/REM 실행은 0회였다. 정수 divider의
65-cycle 지연 단축은 별도 division workload에서 평가하며, 이 CoreMark
timed cycles의 직접 개선 항목으로 보지 않는다. divider 변경이 Fmax에
미치는 영향은 별도 합성·타이밍 검증 대상이다.

## 기존 RV32 비교의 의미

과거 TIM과 같은 ELF를 현재 캐시 구조에서 실행한 기록은 다음과 같다.
이 표는 새 RV64 또는 벡터 성능을 나타내지 않는다.

| 구성 | cycles | instructions | IPC | CoreMark/MHz 추정치 |
|---|---:|---:|---:|---:|
| 과거 TIM 기록, 2 iterations | 437,950 | 576,450 | 1.316246 | 4.566731 |
| 캐시 구조, 동일 RV32 ELF | 513,076 | 576,450 | 1.123518 | 3.898058 |

고정 ELF SHA-256:
`33fe48d15f11a4a396d821fa1feecac527e8322a6af61b8797debb2f02af69ac`.
TIM은 보존된 과거 실행 기록이다. 원본 로그·현재/과거 RTL 구분은
[캐시 사이클 분석](CACHE_CYCLE_ANALYSIS.md)에 있다.

## 개선 후보와 검증 순서

같은 RV64 H/V 모델에서 각 고정 어셈블리 함수를 한 번 워밍한 뒤
두 번째 호출을 측정한 결과다. `profile_rv64_latency.py`가 결과값과
정상 종료를 확인했다. 호출·복귀·CSR의 고정 오버헤드가 포함돼 있어
캐시 자체의 수락→응답 지연과 구분한다.

| 진단 | 연산 수 | 측정 cycles | cycles/연산 |
|---|---:|---:|---:|
| 의존 ADDI chain | 128 | 148 | 1.156250 |
| 같은 비영 source·반복 목적지 ADDI stream | 256 | 328 | 1.281250 |
| x0 source·반복 목적지 ADDI stream | 256 | 276 | 1.078125 |
| 의존 LD pointer chain | 128 | 454 | 3.546875 |
| 독립 LD, 서로 다른 뱅크 | 256 | 282 | 1.101562 |
| 독립 LD, 같은 뱅크 | 256 | 281 | 1.097656 |
| 같은 워드의 연속 SD | 128 | 920 | 7.187500 |

같은 ELF를 다시 실행해 일곱 진단의 cycles가 일치함을 확인했다.
숫자는 해당 함수 배치와 predictor/frontend 상태의 영향을 받으므로
다른 배치의 결과를 같은 ELF 결과로 합치지 않는다.
이 load stream에서는 뱅크를 나눠도 전체 코어 처리량 차이가 거의 없었다.
블록 테스트가 확인한 cache의 동시 두 read 기능과, frontend·AGU·LQ·
completion을 통과한 지속 load 처리량은 별개다. 이 결과만으로 어느 한
단계를 원인으로 확정하지 않으며 각 단계의 valid/ready와 bubble을 계측해야 한다.

| 우선 검토 | 현재 구조의 제약 | 개선 후보 | 확인할 지표·보존 조건 |
|---|---|---|---|
| store 처리 | 일반 store는 commit 시 store buffer에 들어가며, write-through 응답을 기다리는 drain이 느리면 buffer 압력으로 retire가 막힐 수 있다. MMIO는 직접 완료를 기다린다 | 응답 경로 단축, 가능한 store 병합 및 commit된 store 처리량 개선 | SB 점유·enqueue backpressure·bus 완료·retire 대기를 함께 계측, 같은 ELF cycles; precise fault·MMIO·FENCE·snoop 순서 보존 |
| 지속 issue/operand 공급 | 이 ADDI stream에서도 2 instructions/cycle의 지속 처리량이 관찰되지 않았다 | frontend 큐·dispatch·IQ 선택·PRF 읽기·result FIFO의 bubble과 backpressure 계측 | register 선택과 코드 배치별 분리, 동일 ELF의 issue/execute/WB/retire 기록 |
| 지속 load 공급 | 독립 LD 진단이 서로 다른 뱅크에서도 약 1개/cycle 수준 | frontend/AGU/LQ 선택·refill/완료 경로의 bubble 확인 | 각 단계의 매 cycle 두 요청·두 완료 가능 여부, same/different-bank 분리; ordering/flush/PMP 보존 |
| load-use와 분기 | 리스트 추적과 CRC에는 의존성·분기가 있다 | forwarding/응답-to-use 경로와 branch recovery 검토 | retire 공백이 집중된 함수·PC, load-use/redirect 실제 계측; gap을 원인으로 단정하지 않음 |
| miss 처리 | 64B refill을 AXI64 single-beat 여덟 번으로 요청, 제한된 outstanding | 실제 burst refill, 이후 다중 miss/독립 요청 중첩 | 같은 ELF의 cold/steady cycles, AR/R beat, 오류·backpressure·snoop/refill 경합 |
| 벡터 메모리 | 벡터는 별도 메모리 head 경로에서 원소별 접근 | L1의 두 뱅크를 이용한 벡터 공급, 정렬된 접근 결합 | 실제 벡터 load/store 대기·전송 수; 마스크·PMA·부분 fault/vstart 보존 |
| 벡터 실행 중첩 | 벡터 명령이 serial barrier이며 뒤의 scalar dispatch를 막는다 | 독립 scalar/vector 실행 중첩, 이후 벡터 의존성·rename/scheduling | 유용 작업당 cycles; precise trap·분기 취소·메모리 순서 검증 선행 |
| compiler | auto-vectorizer의 cost model과 현재 원소 순차 엔진의 비용이 다를 수 있다 | O2/O3/RVV 실측 후 LTO·loop/code 배치 등을 별도 비교 | 모든 옵션 공개, CRC 일치; static V와 실제 실행된 V를 구분 |
| divider, 별도 workload | 현재 radix-2의 64/32회 반복, 모듈 일반 지연 65/33 cycles | radix-4 및 선행 0·작은 피연산자·2의 거듭제곱 빠른 경로 검토 | signed/W·0 나누기·overflow·flush·backpressure, cycle과 합성 Fmax/PPA 함께 비교; 현재 RTL에는 미적용 |

2 KiB 데이터는 D-cache 용량보다 작다. cold miss와 steady-state hit를
구분하고 miss가 충분히 작으면 prefetch를 CoreMark의 첫 개선으로 택하지 않는다.
prefetch·burst·다중 outstanding의 효과는 별도 스트리밍/큰 working-set에서도 확인한다.

벡터 명령 하나는 여러 원소의 일을 한다. scalar와 RVV의 IPC만 비교해서
성능을 판단하지 않으며 같은 작업의 cycles/iteration과 CoreMark/MHz를 우선한다.
위 항목은 설계 후보이고 아직 측정하지 않은 개선율을 보장하지 않는다.

## 재현

```powershell
python scripts/run_coremark_rv64.py --iterations 2 10
python scripts/profile_rv64_latency.py --repeat
python scripts/report_coremark_rv64.py
```

완료된 2회 세 빌드만 별도로 감사하려면 `python scripts/report_coremark_rv64.py --short-comparison`을 사용한다.
이 모드는 `complete_benchmark_plan=false`인 별도 근거 파일을 만들며,
기본 모드는 여섯 실행 전체가 완료돼야 통과한다. 중단 후에는
`python scripts/run_coremark_rv64.py --iterations 2 10 --resume`으로 해시가 일치하는 완료 결과만 재사용한다.
10회 결과를 포함해 현재 완료된 실행만 감사할 때는 `--completed-runs`를 사용한다.
이 모드도 전체 계획 완료로 표시하지 않으며 별도 진행 근거를 생성한다.

원본 ELF·벡터화 보고서·disassembly·로그·retire CSV는 `out/`에 생성된다.
최소 iteration의 세 실행은 `start_time` 진입부터 `stop_time` 진입까지
retire 공백, dual retire, 명령 분포와 실행된 벡터 명령을 집계한다.
이 구간은 CSR timed window와 경계가 다르며 cache/engine 카운터는 전체
프로그램 범위다. engine busy 값은 서로 겹칠 수 있어 stall 합계로 더하지 않는다.

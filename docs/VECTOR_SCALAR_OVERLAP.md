# Non-memory vector / scalar overlap

기준 소스는 `a49f7a9`다. 이 단계는 vector register 연산과 config의 전역
dispatch barrier를 줄여 독립 scalar가 먼저 실행되도록 한다. Vector 자체는
여전히 ROB head의 단일 owner가 순서대로 실행한다. Vector-vector OoO,
중앙 vector scoreboard, 통합 Permutation/Load/Store unit이나 128-bit memory
issue를 구현했다는 뜻은 아니다.

## 구현

- `rv_decode2`: vector memory는 serializing을 유지한다. Non-memory vector는
  scalar rename/issue를 막지 않는다. 결과와 예외는 기존 ROB의 순서 있는
  completion/retirement로 확정한다. Younger store/MMIO의 외부 효과도 기존
  commit/head 조건을 따른다.
- `vector_start`: non-memory vector는 accepted scalar memory traffic의 완료를
  기다릴 필요가 없다. Memory vector의 `lsu_memory_idle` 조건은 유지한다.
  현재 LSU의 idle은 queued MMIO 항목만으로 내려가지 않는다. 초기의
  "queued MMIO 때문에 순환 대기" 가설은 실제 구현과 달랐으며, 이번 변경의
  근거는 진행 중인 전송과 연산의 중첩이다.
- FP read port 7: vector의 scalar FP operand는 request acceptance에 캡처한다.
  이후 이 포트를 lane 1의 FP retirement 읽기에 돌려준다. Vector와 scalar FP가
  함께 retire할 때도 trace가 younger FP 결과를 읽는다.
- System wakeup: 기존의 지연된 ready/tag와 함께 실제 result data도 등록한다.
  이전에는 이 포트의 data가 0이었다. 대기 중인 scalar consumer가 생기자 IQ의
  LSU base cache가 0을 캡처했고 기존 PRF-equivalence assertion이 이를 잡았다.
  `vmv.x.s` → dependent load로 좁혀 재현한 뒤 수정했다. Ready timing과
  기존 assertion을 유지하며 head control에서 IQ로 새 조합 경로를 만들지 않는다.

## 변경한 동작의 확인

`run_vector_scalar_overlap.py`는 같은 ELF를 Sail, native core, observer wrapper에
실행한다. 현재 145개 reference events가 일치한다. Scalar RAW/WAW,
old physical FP source capture, vector result를 쓰는 load base, cold SRAM refill,
ordered MMIO, branch recovery, illegal vector group과 younger scalar/FP/store
취소를 포함한다.

- Independent scalar execution during a vector: 57건.
- Independent FP execution during a vector: 6건.
- Vector + lane-1 FP co-retirement: 2건.
- Scalar memory engine이 busy인 동안 non-memory vector 시작: 3건.
- Older accepted vector를 보존한 younger branch recovery: 1건.
- Illegal vector trap: 1건. Younger architectural effects는 남지 않는다.

`run_vector_scalar_irq.py`는 vector DIV가 실행 중일 때 PLIC source 1을 주입한다.
Start=282, pending=283, retire=430, interrupt accept=431이며 scalar overlap 1건을
관찰했다. Handler에서 완성된 vector result, vstart=0과 claim ID를 확인하고,
복귀 후 scalar 결과도 확인한다. 유한한 directed IRQ 사례다.

공유 SRAM/Sv39 alias 8개 사례의 Sail/RTL events 936건, vector state의
22개 SEW/LMUL configuration 및 7,040개 64-bit words, VS/VU partial memory
fault와 restart도 변경 후 모델에서 통과했다. 전체 profile/release 회귀의
대체물은 아니다.

Zero-data wakeup 대조군은 `check_vector_system_wake_negative.py`에서 별도
backend copy의 system wake data만 0으로 바꾸고 같은 overlap ELF를 실행한다.
기존 load-base assertion에서 실패해야 하며 생산 RTL은 수정하지 않는다.
같은 ELF의 isolated zero-data mutant가 기존 load-base assertion에서 실패하는
expected-failure 실행을 완료했다. 생산 RTL의 같은 프로그램은 통과했다.

## 짧은 성능 진단

기존 고정 ELF의 각 함수를 한 번 워밍한 후 128회 명령의 두 번째 호출을 측정했다.
Call/return/CSR 및 frontend 비용을 포함한다. Unit 자체의 latency는 아니다.

| 경로 | a49f7a9 cycles | 변경 후 cycles | 감소율 |
|---|---:|---:|---:|
| Scalar ADD | 148 | 148 | 0.00% |
| VSET | 1,030 | 783 | 23.98% |
| VADD | 1,534 | 1,295 | 15.58% |
| VLE64 | 3,285 | 3,285 | 0.00% |
| VLE32 | 5,333 | 5,385 | -0.98% |
| VLUXEI64, data SEW64 | 3,298 | 3,298 | 0.00% |
| VSLIDEDOWN | 1,534 | 1,295 | 15.58% |

VLE32 진단의 증가도 포함해 기록한다. 이 단계는 vector memory engine의
처리량을 바꾸지 않았으며, 주변 config/call/dispatch 비용이 포함된 측정이다.

CoreMark는 `compare_vector_overlap_performance.py --coremark-iterations 2`
또는 `10`으로 이전 ELF를 재컴파일하지 않고 실행한다. 변경 전 binary와
10회 결과는 `out/performance/vector_overlap_before/`에 보존했다.
2회/10회 최종값은 각각의 report가 `passed=true`가 된 뒤 추가한다.

실제 Fmax/STA는 측정하지 않았다. Pipeline/cache 1차 변경과 당시 CoreMark
10.88% 개선은 [이전 작업 기록](VECTOR_PIPELINE_REWORK.md)을 참조한다.

## CoreMark 2회 결과

같은 2회 ELF에서 cycles는 **2,059,072→1,853,468**,
**9.99% 감소**했다. IPC는 0.268299→0.298061,
retired instructions는 양쪽 552,447개이며 CRC가 일치했다.

주소 캐시 오류가 발생했던 첫 CoreMark 실행은 실패로 보존했으며, 위 수치는
등록된 system wake data 수정 후 재실행한 결과다. 10회 결과는 실행 중이다.

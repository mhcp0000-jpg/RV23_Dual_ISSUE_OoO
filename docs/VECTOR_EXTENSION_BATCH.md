# Vector extension batches and memory issue

기준 소스는 `bdc6f37`이다. 이번 단계는 기존 128-bit 정수 pipeline을
부호·제로 확장에도 사용하고, active vector memory element의 요청 전에
소모하던 control bubble을 제거한다. 기존 CoreMark ELF를 재컴파일하지 않는다.

## 구현

- `rv_vector_engine`: `vzext`/`vsext`도 packed issue한다. 좁은 source 원소를
  destination SEW의 slot에 배치한 뒤 operand register에 저장한다.
  SEW16/32/64와 합법적인 VF2/4/8의 여섯 조합을 고정 bit slice로 연결한다.
  Destination row 경계가 batch를 제한하므로 더 좁은 source도 해당 row를
  넘지 않는다. 기존 mask, vstart, VL 및 write mask가 유지된다.
- `rv_vector_simd_alu`: 두 64-bit lane에서 고정 배선과 sign-bit 복제로
  확장한다. 모든 element ALU에 동적 extension 폭 계산을 복제하지 않는다.
  SEW16은 최대 8개, SEW32는 4개, SEW64는 2개 원소를 한 batch로 처리한다.
  연속 batch의 issue interval은 1사이클이다. 명령 간 issue interval이나
  전체 명령 latency가 1사이클이라는 뜻은 아니다.
- Memory: active element의 주소와 데이터가 준비된 `ELEMENT`에서 head가
  ready이면 즉시 요청을 수락하고 `MEM_WAIT`로 간다. Backpressure 때는
  기존 `MEM_ISSUE`에서 같은 요청을 유지한다. Segment의 후속 field와
  translation/PMP/PMA, fault-only-first, precise fault 경로는 유지한다.

## 성능 진단

같은 진단 ELF를 변경 전·후 native full-core 모델에 실행했다. 각 함수를
한 번 워밍한 후 128회 명령의 두 번째 호출을 측정했다. 아래 수치는
frontend/call/CSR 비용을 포함하며 독립 실행 유닛 latency가 아니다.

| 경로 | 변경 전 cycles | 변경 후 cycles | 감소율 |
|---|---:|---:|---:|
| Scalar ADD | 148 | 148 | 0.00% |
| VSET | 783 | 783 | 0.00% |
| VADD / VSLIDEDOWN | 1,295 | 1,295 | 0.00% |
| VLE64 | 3,285 | 3,029 | 7.79% |
| VLE32 | 5,385 | 4,873 | 9.51% |
| VLUXEI64 | 3,298 | 3,046 | 7.64% |
| VZEXT16 / VSEXT16 | 2,191 | 1,295 | 40.89% |
| VZEXT32 | 1,680 | 1,296 | 22.86% |
| VSEXT32 | 1,679 | 1,295 | 22.87% |
| VZEXT64 / VSEXT64 | 1,423 | 1,295 | 9.00% |

같은 **CoreMark 2회 ELF**의 cycles는 **1,853,468→1,815,477**로
**2.05% 감소**했고 IPC는 **0.298061→0.304299**다. Retired instructions는
양쪽 552,447개이며 CRC `[e9f5, e714, 1fd7, 8e3a]`가 같다.
10회 측정은 실행 중이며 이 2회 값을 10회 결과로 대신하지 않는다.
완료된 진단과 회귀의 소스 해시 근거는
[evidence snapshot](evidence/vector_extension_batch.json)에 보존한다.

## 変更箇所の確認

- SIMD: 독립 값 계산과 대조한 7,808 cases / 57 forms.
- Integer owner: 3,041 packets. 합법적인 SEW/LMUL/VF, mask, vstart,
  tail, group/row 경계, 허용된 source/destination overlap 및
  불법 fractional LMUL의 거부를 포함한다.
- Pipeline: extension 248 issues, 8 batches의 8사이클 연속 issue와
  8원소 병렬 처리, pending RF write의 completion 전 drain을 관찰했다.
- Memory owner: 9,119 packets / 2,756 physical bytes.

Native M/HS/VS H/V 통합, 같은 ELF의 scalar/vector overlap 145 reference
events, non-memory vector 중 PLIC interrupt의 retire 경계, vector memory 중
PLIC claim 순서, FENCE·atomic·CBO.ZERO·debug 동시 접근도 변경 후 모델에서
통과했다. Zero-data system wake 대조군은 기존 load-base assertion에서
실패했다. 84,348개 paired latency probes / 231 forms와 secret-dependent
VCLZ 대조군도 통과했다. FP owner 235 packets도 회귀했다.

위 component 확인은 이번 변경 범위의 회귀이며 전체 RVA23S64 적합성이나
물리 타이밍 sign-off를 대신하지 않는다. 실제 Fmax/STA는 측정하지 않았다.

## 재현 및 다음 병목

```powershell
python scripts/profile_vector_latency.py --baseline-dir out/performance/vector_batch_before --output-dir out/performance/vector_batch_latency --include-extensions
python scripts/compare_vector_overlap_performance.py --coremark-iterations 10 --baseline-dir out/performance/vector_batch_before --output-dir out/performance/vector_batch --before-commit bdc6f37 --expected-changes rtl/backend/rv_vector_engine.sv rtl/backend/rv_vector_simd_alu.sv
```

이 비교에는 로컬에 보존된 변경 전 executable/model/report가 필요하다.
일반 기능 검사는 `run_vector_simd_checks.py`, `run_vector_integer_engine_checks.py`,
`run_vector_pipeline_checks.py`, `run_vector_memory_engine_checks.py`로 실행한다.

현재 vector memory는 공유 D-cache를 통과하지만 원소 단위 <=64-bit 요청과
단일 pending memory transaction을 사용한다. 다음 성능 작업은 contiguous
load/store의 bank 활용과 요청·응답 중첩이다. 사용자가 제안한 통합
Permutation/Load/Store unit 및 hazard scoreboard, vector-vector OoO,
128-bit vector memory issue는 이번 변경에 포함되지 않는다.

### 다음 병목을 고르는 관측

`python scripts/profile_vector_occupancy.py`는 생산 RTL을 구동하지 않는
`rv23_vector_performance_tb`에서 보존된 같은 2회 CoreMark ELF를 실행한다.
관측 실행의 전체 CoreMark 패킷이 기존 quiet 실행과 정확히 같아야 한다.
전체 패킷에는 cycle count, instruction count와 CRC가 포함된다.

출력은 `out/performance/vector_occupancy/report.json`이다. `start_time`의
첫 명령 retire부터 `stop_time`의 첫 명령 retire 직전까지 상태별 체류 시간,
각 상태에서 retire가 없던 시간, vector physical request→response latency와
해당 window 전체의 D-cache hit/miss accept 수를 기록한다.
Memory substate는 vector의 `MEM_WAIT` 안에서만 집계한다. Window 경계는
CoreMark 내부 counter read 위치와 다르므로 window cycles를 점수 계산에
사용하지 않는다. No-retire와 상태 체류의 겹침도 단독 stall 원인 판정은 아니다.

관측 래퍼는 먼저 기존 H/V ELF로 smoke를 통과했다. 이 window에서 3,163
cycles, vector physical 요청/응답 각각 8건과 상태별 합계를 확인했다.
CoreMark 관측 실행도 완료했고 기존 quiet 실행과 전체 packet이 같다.
내부 CoreMark 측정은 1,815,477 cycles / 552,447 instructions다.
Retire 경계의 관측 window는 1,815,503 cycles / 552,448 instructions이며
위에서 설명한 경계 차이로 내부 counter와 다르다.

| 관측 | Cycles / count |
|---|---:|
| Vector MEM_WAIT | 166,149 cycles |
| 그중 TRANSLATE / WAIT_TRANSLATE / CHECK / MEMORY_REQUEST / RESULT | 각각 26,596 cycles |
| 그중 MEMORY_RESPONSE | 33,169 cycles |
| 물리 vector 요청 / 응답 | 각각 26,596건 |
| 요청이 ready를 기다린 시간 | 0 cycles |
| Window 전체 D-cache hit / miss accept | 106,591 / 35건 |
| Vector owner CHECK / RESULT | 94,507 / 94,588 cycles |
| Vector owner INT_DRAIN | 102,810 cycles |

이 workload에서 물리 vector 요청 수락→응답은 평균 약 1.25사이클이다.
각 원소마다 그 밖의 다섯 memory-head 제어 상태에 1사이클씩 반복해서
머문다. 따라서 연속 원소의 요청 수를 줄이거나 preflight와 요청·응답을
중첩하는 작업이 현재의 구체적인 개선 대상이다. CHECK/RESULT/INT_DRAIN
등 명령별 owner overhead도 남아 있다. IDLE 1,129,305 cycles에는 scalar
실행과 다른 대기가 섞이므로 이를 전부 vector stall로 계산하지 않는다.

초기 관측은 외부 hierarchical enum 참조의 폭이 잘못 처리되어 memory
하위 상태 합계 검사에서 거부됐다. 외부 조건은 숫자 bin으로 고치고 driver가
실제 두 enum 선언의 순서를 검사하도록 했다. 수정 후 주 상태와 하위 상태의
합계 및 같은 benchmark packet을 다시 확인했다.
[완료된 관측의 소스·로그 해시](evidence/vector_occupancy.json)

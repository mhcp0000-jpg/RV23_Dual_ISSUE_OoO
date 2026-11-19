# Vector execution pipeline rework

사용자가 보고한 경로는 `instruction_q`에서 vector register file의 `live_q`까지다.
기존 구조에서는 decode/SEW·snapshot 읽기 선택·정수 계산·목적지 선택·부분 쓰기가
같은 cycle에 연결돼 있었다. 정수 ALU에는 128비트 중간값의 조합 `/`와 `%`도 있었다.

## 현재 변경

- 모든 register-file 쓰기의 enable·목적지·element·SEW·mask·data를 writeback
  레지스터에 함께 저장한다. slides/FP/memory도 이 경계를 거친다.
- 일반 정수 원소는 operand/control/metadata → ALU result/metadata → writeback →
  register-file update로 진행한다. source snapshot 덕분에 독립 원소를 연속 투입할
  수 있으며, instruction 완료 전 valid와 writeback을 drain한다.
- 일반 정수 연산을 실제 64비트 lane 두 개로 병렬화했다. lane별 SEW subdivision으로
  2×64/4×32/8×16/16×8 원소를 처리하고 snapshot read 및 부분 마스크 write를
  128비트로 확장했다. LMUL8에서는 여덟 128비트 배치를 연속 투입한다.
  vstart·VL·register-row 경계와 실행 마스크로 유효 원소를 한정한다. inactive
  계산값이 live register에 섞이지 않도록 write data에도 bit mask를 적용한다.
  widening/narrowing/extension/reduction/DIV·특수 연산과 FP는 아직 별도 경로다.
- reduction은 누산 결과를 받은 뒤 다음 원소를 보낸다. 목적지·carry/mask·vxrm 및
  element index는 해당 데이터와 함께 보관한다.
- production ALU의 DIV/REM 분기는 elaboration parameter로 제거하고 별도
  `rv_vector_divider`가 SEW 8/16/32/64를 정규화해 반복형 `rv_divider`를 사용한다.
  요청 수락부터 응답까지 68 cycles를 유지해 zero/overflow 데이터별 조기 완료가
  기존 paired timing 계약을 깨지 않게 한다. result backpressure 중 값은 유지한다.
- 곱셈·MAC·round/saturation의 내부 조합 경로는 추가 분할 검토가 남았다.
  이번 단계만으로 벡터 전체의 STA/Fmax 문제가 해결됐다고 판정하지 않는다.

## 확인된 단품 결과

아래는 pipeline/cache 단계 `9332f6c`의 결과다. 뒤의 반복 preflight/완료
bubble 성능 변경 이후 검사는 별도 절에 기록한다.

- 반복형 vector divider: 128개 산술/고정 지연/held-result 사례.
- integer owner: 917개 instruction packet, 네 SEW의 LMUL8 및 lane/group 경계 포함.
- two-lane 산술: 55 forms, 7,040개 packed 입력의 독립 원소 계산 대조.
- throughput observer: 네 SEW 모두 8개의 128비트 배치가 8사이클 연속 투입되고
  결과까지 drain된 뒤 완료. parallel elements=16/8/4/2.
- SIMD mask 오류 대조군: 별도 RTL copy에서 마스크 적용을 제거하면 기존 masked
  add case138이 실패해야 한다. 생산 RTL은 변경하지 않는 expected-failure 검사다.
- FP owner: 235개 packet, mask/restart/flags/half conversion.
- memory owner: 9,119개 packet, physical byte access 2,756개.
- paired latency: 84,348개 probe, 231 forms.

원본 실행 로그는 `out/rva23/vector_pipeline_*_execution.log`와 각 driver의 report에
남긴다. full H/V native 기본 실행과 FENCE/atomic/CBO.ZERO+debug 경합은 통과했다.
현재 SIMD 변경 기준 memory owner 9,119개 packet/2,756개 byte access와
22개 SEW/LMUL 조합의 7,040개 register word 대조도 통과했다. native OoO
검사에서는 기존 dual-bank load 두 건과 dual issue/execute/retire를 관찰했다.
동일 ELF CoreMark 10회 재실행과 후속 fault 검사는 아래 단계별 결과로 기록했다.
전체 scalar/vector ordering·interrupt·ACT·Linux 근거 갱신은 별도로 남아 있다.
기존 통합 기록은 수정 전 `802e2e1` 기준이며 현재 변경의 통과 근거로 재사용하지 않는다.

## Vector memory와 cache

vector/guest/misaligned head 접근을 scalar와 같은 D-cache에 연결했다. 유지보수
CBO 요청은 별도 AXI 경로를 유지한다. transparent request mux는 stall 중 선택과
accepted transaction의 response owner를 보관하며 scalar hit에 등록 단계를 추가하지
않는다. 65개 router transaction과 20개 연속 scalar hit에서 latency=1/II=1을 확인했다.
MMIO·NC 속성은 D-cache의 non-allocation 경로로 전달한다.

동일 ELF의 native scalar/vector SRAM·Sv39 alias 검사에서 vector read 48회 중
47회 hit, vector write 16회 및 data refill read beat 8회를 관찰했고 Sail 이벤트
936건이 일치했다. 이것은 해당 fixture의 관찰이며 CoreMark 개선율이 아니다.
메모리 head는 아직 원소별 최대 64비트 요청이다. 두 D-cache bank의 128비트
동시 vector load 공급 및 unified data unit/scoreboard는 아래 다음 작업이다.

## 합의한 다음 구조

- ALU 실행부는 두 64비트 SIMD lane을 사용한다. 곱셈·MAC의 내부 등록 경계도
  추가 검토하며 ready/valid·mask·index·destination을 같은 packet으로 이동한다.
- Permutation/Load/Store는 하나의 data movement unit으로 묶는다. register-file
  128비트 읽기와 shared D-cache 두 bank의 접근을 중재하고, mask·주소 변환·PMP/PMA·
  page/line 경계·vstart/fault 처리를 유지한다. 이 unit 분리는 아직 구현 전이다.
- 중앙 scoreboard는 LMUL/EEW register group의 RAW/WAR/WAW, v0 암묵 source,
  widening/narrowing 및 vl/vtype/vstart/vxrm·FP 상태 의존성을 관리한다.
- 명령 간 중첩에는 scoreboard뿐 아니라 순서 있는 completion/commit과 미확정
  결과 보관이 필요하다. 더 오래된 load fault 뒤 younger ALU 결과가 live state에
  남거나 younger store/MMIO가 먼저 보이면 안 된다. 현재 단일 owner를 제거하기
  전에 이 recover/commit 경로를 구현하고 검증한다. 아직 중첩 실행을 주장하지 않는다.

실제 Fmax 비교에는 같은 TOP·대상·도구·clock/IO 제약과 새 worst-path 보고서가
필요하다. simulation cycle latency와 physical clock period는 구분한다.


## Data movement unit 분리 체크리스트

사용자의 추가 지시대로 Permutation / Load / Store는 하나의 실행 유닛으로,
정수 ALU는 별도 실행 유닛으로 분리한다. 여기서 하나의 유닛은 공유된 issue / completion
소유권을 뜻하며, cache miss 동안 ALU까지 막는 단일 조합 경로를 뜻하지 않는다.
이 절은 구현 순서이며 아래 미완료 항목은 현재 기능으로 광고하지 않는다.

- [x] 2×64비트 integer SIMD와 128비트 source read / masked write 경로.
- [x] scalar/vector가 같은 D-cache를 사용하고 response owner를 보존.
- [x] 모든 vector register write의 명시적인 writeback 경계.
- [ ] permutation의 index / gather / slide / compress 제어와 load/store 주소 및
  응답 제어를 data movement unit으로 이동. 변환 및 PMP/PMA 검사를 유지.
- [ ] memory 요청과 완료는 ready/valid handshake로 분리. cache miss 또는 응답
  backpressure 중 index / mask / 주소 / 목적지를 유지하고 요청을 중복 발행하지 않음.
- [ ] 동시에 두 bank를 읽는 128비트 vector load. 우선 두 접근 모두 유효함을
  검증할 수 있는 aligned RAM 영역에 적용하고 page / mask / MMIO / 예외는 별도 처리.
- [ ] 중앙 issue hazard 판정: 실제 EEW/LMUL register group의 RAW/WAR/WAW,
  implicit v0, scalar source 및 vector CSR / FP rounding 상태 의존성.
- [ ] 여러 명령이 실행되는 동안 각 명령의 source snapshot과 결과 소유권 분리.
  현재 단일 snapshot을 그대로 두고 두 번째 명령을 수락하면 안 됨.
- [ ] ordered completion / commit 및 exception recovery. 미확정 younger 결과는
  live register 대신 별도 보관하고, store/MMIO 외부 효과는 순서가 확정된 뒤 허용.
- [ ] ALU와 data movement unit의 독립 명령 중첩 검사. 긴 load miss + 독립 ALU,
  load→ALU RAW, ALU→store RAW, permutation group overlap, v0 write→masked op,
  older load fault + younger ALU, interrupt + pending writeback을 포함.
- [ ] 곱셈 / MAC 내부 pipeline 분할과 동일 제약에서 실제 STA 재측정.

예: `vle v8` 뒤 `vadd v16,v20,v24`는 register group과 상태가 독립적이면 중첩
후보다. 반면 `vadd v16,v8,v24`는 load 결과를 기다려야 한다. 앞선 load가 fault를
내면 독립적인 younger add도 architectural state에 남기지 않는 것이 완료 순서의
역할이다. 레지스터 scoreboard만으로 이 조건이 충족되지는 않는다.

첫 번째 동일 ELF 10회 재실행은 완료했다. O2 scalar 4,896,919 cycles /
2,997,696 instructions / IPC 0.6121596, O3 scalar 4,902,692 cycles /
3,036,405 instructions / IPC 0.6193342로 기존과 같았다. RVV는 11,525,110
cycles / 2,762,088 instructions / IPC 0.2396583으로 기존 11,396,161 cycles보다
1.13% 증가했다. 이 결과는 아래 성능 개선 전의 pipeline/shared-cache 단계다. SYNTHESIS macro를
사용한 Verilator elaboration/lint도 완료했지만 경고가 있으며 실제 합성/STA 결과가 아니다.


## 성능 개선 1차: 반복 preflight와 완료 bubble 축소

변경 전 소스는 `9332f6c`에 보존했다. full RV64 H/V native model 입력의
모든 RTL/TB/include bytes가 해당 checkpoint와 같은지 확인했다. 변경 후
모델의 차이는 `rv_vector_engine.sv`와 `rv23_hypervisor_memory_head.sv` 두 파일이다.

기존 indexed 64-bit load는 natural alignment가 맞아도 8개 바이트 각각의 주소
변환/검사를 거쳤다. 자연 정렬된 최대 8바이트는 최소 4 KiB page와 8-byte bus word를
넘지 않는다. 첫 바이트의 변환/PMA 검사와 전체 폭의 PMP 허가가 모두 성공하면
그 변환으로 단일 physical request를 진행하도록 변경했다. 전체 PMP 허가가 없거나
misaligned인 경우에는 기존 byte preflight와 fault 우선순위를 유지한다.
따라서 두 PMP entry가 허가한 각각의 바이트를 합쳐 잘못된 aligned access를 허용하지 않는다.

일반 integer instruction은 ALU valid가 비고 마지막 RF write가 소비되는 edge에서
완료 상태로 이동한다. reduction의 FINISH accumulator write는 별도로 유지한다.
다른 특수 경로도 실제 pending write가 없는 경우에만 WB_DRAIN을 생략한다.

- `compare_vector_preflight.py`: 같은 functional/backpressure stream에서 byte
  control 3,668 → aligned fast path 3,428 cycles. CHECK 523 → 443,
  aligned CHECK 162 → 82. Physical transactions는 양쪽 416건으로 같다.
- 변경 후 integer owner 917, memory owner 9,119, FP owner 235개 사례 통과.
  128-bit throughput/drained-completion observer도 통과했다.
- 전체 코어 비교는 `profile_vector_latency.py`의 같은 ELF와 저장된 이전 native
  binary를 사용한다. CoreMark는 `compare_coremark_vector_fastpath.py`가 기존
  10회 ELF를 재컴파일하지 않고 CRC/retired instruction count까지 비교한다.
- 이번 변경은 cycle 수를 줄이는 변경이다. 실제 STA/Fmax 개선을 뜻하지 않는다.

### 같은 ELF 전체 코어 latency probe 결과

각 함수는 먼저 한 번 워밍하고 128회 명령의 두 번째 호출을 측정했다.
call/return/CSR/frontend 비용이 포함되며 유닛 자체의 latency는 아니다.
수정 전/후 native binary에 동일 ELF를 사용했고 결과값도 확인했다.

| 경로 | 변경 전 cycles | 변경 후 cycles | 감소율 |
|---|---:|---:|---:|
| scalar_add | 148 | 148 | 0.00% |
| vset | 1,030 | 1,030 | 0.00% |
| vadd | 1,877 | 1,534 | 18.27% |
| vle64 | 8,789 | 3,285 | 62.62% |
| vle32 | 10,069 | 5,333 | 47.04% |
| vluxei64 | 8,789 | 3,298 | 62.48% |
| vslidedown | 1,621 | 1,534 | 5.37% |

원본 보고서: `out/performance/vector_latency/report.json`. CoreMark 10회 비교는
`out/performance/vector_fastpath/o3_rvv.json`이며 `passed=true` 전에는 완료로 취급하지 않는다.

### CoreMark 2회 같은 ELF 진단

반복 횟수 2회의 기존 ELF를 재컴파일하지 않고 저장한 수정 전 native binary와
수정 후 native binary에 각각 실행했다. CRC와 retired instruction count는 같았다.
이것은 10회 측정의 대체물이 아니라 성능 원인 분석용 trace 실행이다.

- cycles: 2,309,935 → 2,059,072, 감소율 10.86%.
- IPC: 0.239161 → 0.268299.
- 두 기록은 start_time → stop_time의 retire 공백을 다음 mnemonic에 귀속한다.
  이는 원인별 stall cycle 분해가 아니다.

| mnemonic | 명령 수 | 전 gap 귀속 | 후 gap 귀속 |
|---|---:|---:|---:|
| vluxei64.v | 8,208 | 348,956 | 266,876 |
| vzext.vf2 | 8,208 | 127,235 | 102,611 |
| vadd.vv | 8,640 | 116,590 | 90,670 |
| vsll.vi | 8,424 | 119,376 | 94,104 |
| vsetvli | 15,552 | 95,918 | 95,920 |
| vsetivli | 10,113 | 63,957 | 63,955 |

CoreMark의 `vluxei64.v` 뒤 64는 **index EEW**다. 실제 주요 gather는
`vsetvli ... e16,mf2` 이후의 16비트 data load이며, 위 VLE64/VLUXEI64
진단 함수의 64비트 data load와 구분한다. 주소 계산/변환 및 원소별 요청 비용과
잦은 vset/non-memory vector dispatch barrier가 다음 개선 후보로 남는다.

원본: `out/performance/vector_fastpath_profile/before.json`, `after.json`.

### 다음 성능 후보의 구현 제약

현재 `rv_decode2`는 모든 vector op를 serializing으로 표시한다. 이 표시는
backend의 UQ/decode/dispatch barrier와 ROB의 두 번째 retire 억제에 연결된다.
non-memory vector는 여전히 ROB head에서 순차 실행하되, 독립 scalar를 먼저
rename/issue하도록 허용하는 것이 다음 후보이다. 이것은 vector-vector OoO나
Permutation/LSU 통합 구현과는 별도 단계이며 아직 RTL에 적용하지 않았다.

serializing bit 하나만 제거하면 안 된다. `vector_start`가 무조건
`lsu_memory_idle`을 기다리므로, 뒤의 ordered MMIO 요청이 LSQ에 들어와
head를 기다리면 앞 vector와 순환 대기가 생길 수 있다. non-memory vector의
시작 조건도 함께 분리하고, memory vector/FENCE/CSR의 barrier는 유지해야 한다.
검사 대상은 vector→younger scalar RAW/WAW rename, speculative branch squash,
vector exception + younger physical result, pending MMIO, CSR FS/VS dirty visibility,
interrupt와 scalar/vector memory ordering이다. 단일 vector owner의 snapshot과
순차 head 실행은 유지하므로 이 단계에서 여러 vector instruction의 동시 실행을
광고하지 않는다.

### CoreMark 10회 최종 결과

- 같은 ELF SHA-256: `59c583cf167435f458d4186d2083fdeb4917f56e5ff71c30e8a3dd03990742e1`. 재컴파일하지 않았다.
- cycles: 11,525,110 → **10,270,851**, **10.88% 감소**, 속도 1.122배.
- IPC: 0.239658 → **0.268925**.
- CoreMark/MHz 추정: 0.867671 → **0.973629**.
- retired instructions: 양쪽 **2,762,088**, CRC e9f5/e714/1fd7/8e3a 일치.
- 이 수치는 2회 trace 진단과 구분한 최종 10회 측정이다.
- 기존 O3 scalar 4,902,692 cycles 기준과 비교하면 RVV는 여전히 약 2.09배
  많은 cycles를 사용한다. scalar/vector 실행 중첩이나 128-bit vector memory
  issue는 아직 적용되지 않았다. 실제 합성 Fmax 개선은 측정하지 않았다.

[공개 측정 snapshot](evidence/vector_fastpath.json).
재현 driver: `scripts/compare_coremark_vector_fastpath.py`,
`profile_vector_latency.py`, `profile_coremark_vector_fastpath.py`,
`compare_vector_preflight.py`. 기존 10회 ELF와 변경 전 native 모델은
`out/performance/vector_fastpath_before/` 및 기존 CoreMark output에 보존했다.

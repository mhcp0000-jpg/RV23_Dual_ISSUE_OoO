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
새 native 모델을 기준으로 scalar/vector ordering·interrupt/fault·ACT·Linux와
동일 ELF CoreMark 10회 재실행을 완료해야 전체 통합 근거가 갱신된다.
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

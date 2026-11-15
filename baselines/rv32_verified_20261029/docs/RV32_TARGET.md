# 현재 목표: RV32 구성과 검증 회귀

사용자의 RV32 전환 지시가 이전 RVA23S64 계획을 대체한다. RV32는 여기서 프로젝트의
하드웨어 구성 이름이며 공식 RVA23 호환성을 뜻하지 않는다. 기존 폴더와 rv23_ 모듈
prefix는 경로 호환성을 위해 유지한다.

- 기본 ISA/ABI: RV32IMFC_Zicsr_Zifencei / ilp32f, XLEN32, FLEN32, PA32.
- M/U 모드, PMP 8개, machine interrupt. A/D/V/S/MMU/표준 Debug Module 미지원.
- 2-wide OoO core, I/D 각 32 KiB, 64-byte cache line, AXI4, 공용 SRAM 1 MiB.
- 외부 AXI data 64 bit, 각 L1 내부 64-bit 2-bank. IF 128-bit 및 서로 다른 bank의
  두 LSU hit는 1-cycle 동기 읽기와 동시 수락을 검증한다.
- 기존 원본 RTL과 원본 검증 산출물을 바꾸지 않는다. 새 RTL로 다시 실행하고 입력과
  실행 결과를 hash로 묶는다. 과거 RV64 PASS를 RV32 PASS로 옮겨 적지 않는다.

완료 gate:

1. RTL 기본값, 빌드 ISA/ABI, 실행 테스트와 현재 문서를 RV32로 일치시킨다.
2. 기존 유지 가능한 unit/block/parameter 회귀와 backend 통합 회귀를 반입하고 실행한다.
   실제 ROB48/SEQ8의 sequence 예산 소진·복구·wrap도 검증하고, dispatch와 ROB
   allocation의 원자성을 확인한다.
3. 기존 exact-rational RV32F oracle를 static/dynamic rounding으로 재실행한다.
4. 새 cached SoC에서 RV32 C/정수/FP/CSR/PMP 및 CoreMark CRC 소프트웨어 검증을 실행한다.
5. 캐시/버스 추가 검증: seeded random scoreboard, byte mask, backpressure, refill 오류와
   invalidate race, reset/경계, dual LSU; 실제 MSIP/MTIP/MEIP handler, 자기수정 코드와
   FENCE.I, native halt/drain/resume 및 debug AXI 접근을 검사한다.
6. 요구 목록·각 실행의 입력/결과·남은 한계를 감사하고 재현 runner와 문서를 남긴다.
7. 캐시 성능 변경은 같은 ELF의 2회/10회 실행과 retire control stream을 비교한다.
   hit 경로 지연, bank 충돌/동시성, 다른 word 쓰기에 의한 과도한 stall을 검사한다.

TIM 전용 fabric/top의 과거 TB는 새 구조에 해당하지 않는다. 대응하는 새 SRAM/cache
통합 회귀로 대체한다. 과거 특정 timing 후보/참조 버전에 대한 비교 실험은 현재
기능 검증을 대신하지 않는다. 전체 ISA 인증/장기 differential/STA는 별도 범위이며
좁은 smoke 결과로 이를 통과했다고 주장하지 않는다.

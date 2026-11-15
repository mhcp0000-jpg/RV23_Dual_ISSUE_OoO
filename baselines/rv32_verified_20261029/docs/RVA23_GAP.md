> 역사 문서: 이전 RVA23S64 계획이다. 현재 사용자 목표는 [RV32_TARGET](RV32_TARGET.md)이며 이 계획을 대체한다.

# RVA23S64 목표와 현재 범위

기준: [RISC-V RVA23 Profiles 1.0](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html).
RVA23은 RV64 기반 U/S 프로파일이다. 이 표는 작업 분류이며 공식 적합성 판정표를
대체하지 않는다. 기존 프로젝트의 RV32 시험 결과를 새 SoC의 검증 결과로 옮기지 않는다.

| 영역 | 현재 | 후속 완료 조건 |
|---|---|---|
| RV64I/M/C/Zicsr/Zifencei | 재사용 RTL의 XLEN64 구성, 회귀 필요 | RV64 ISA differential/arch-test |
| F | 기존 single-precision FPU 재사용 | RV64 통합·CSR·exception 회귀 |
| A / reservation / Za64rs / Zawrs | 미구현 | LR/SC/AMO, 버스 atomicity, forward-progress |
| D, Zfhmin, Zfa | 미구현 | FP64 datapath/rounding/flags 및 FP16/추가 연산 |
| B, Zicond, Zcb, Zimop, Zcmop, hints | 개별 감사·추가 필요 | mandatory opcode 전부, illegal instruction 정확성 |
| V / Zvfhmin / Zvbb / Zvkt | 미구현 | vector state/rename/execute/LSU/trap/save-restore |
| Zicntr / Zihpm / Zkt | 일부 CSR만 존재, 적합성 미증명 | 필수 counter와 latency 계약 전부 감사 |
| Zic64b / Zicbom / Zicbop / Zicboz | 64B cache line만 구현 | cache-management/zero/prefetch 명령과 권한 |
| Ziccif/Ziccrse/Ziccamoa/Zicclsm | 미증명 | PMA, misaligned access, atomicity/order |
| Supm / Ssnpm | 미구현 | pointer masking와 mode 제어 |
| Ss1p13, Svbare/Sv39, Svade, Svpbmt, Svinval, Svnapot | MMU/S-mode 미완성 | CSR/privilege, ITLB/DTLB/PTW, fault, translation fence |
| Sstc / Sscofpmf / Ssu64xl | 미구현 | supervisor timer/counter filtering/mode 요구 |
| Sha (H와 stateen/가상화 관련 요구) | 미구현 | VS/HS, 2-stage translation, 가상 interrupt/CSR |
| SRAM/PLIC/CLINT | 새 main AXI에 통합 | directed regression 결과 별도 기록 |
| 표준 external debug | native halt/AXI/trace 포트만 | Debug Module + JTAG/DTM/DMI + CSR/명령 접근 검증 |

진행 순서: ① SRAM/캐시/IRQ/native debug 기능 기반 → ② RV64 scalar 전체 감사 및
A/B/D/추가 mandatory scalar → ③ S-mode/Sv39/PTW/TLB → ④ V와 vector mandatory →
⑤ H/Sha 및 나머지 mandatory → ⑥ 공식 arch-test·Sail/Spike differential·성능/STA.
후속 단계는 장기 목표이며 이 시작본을 RVA23 compliant라고 부르지 않는다.

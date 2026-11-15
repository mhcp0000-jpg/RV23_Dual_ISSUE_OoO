# 2026-10-28 초기 통합 검증

수정된 최종 RTL로 아래 테스트를 실제 실행했다. 저장된 소스 및 테스트/실행파일 SHA256은
`verification_snapshot.json`, 재현 로그는 `../out/`에 있다.

| 검사 | 결과 | 범위 |
|---|---|---|
| pyslang 11.0.0 | PASS, 오류 0 | 51 RTL source, XLEN32/64 두 top elaboration |
| rv23_memory_tb | PASS, 42 checks | I/D hit/miss/refill/replacement, byte strobe, debug 쓰기 snoop, FENCE.I invalidate 입력, 두 LSU, 1MiB 끝주소/잘못된 주소, CLINT/PLIC, 응답 backpressure, reset 후 SRAM 보존 |
| rv23_cache_fault_tb | PASS, 10 checks | refill 오류/부분라인 무효, write 오류, device bypass, refill 중 invalidate, downstream stall |
| rv23_boot_tb | PASS, 61 retired instructions 관측 | 실제 RV64 core의 SD/LD/SB/LHU, 분기, FENCE/FENCE.I, CLINT MMIO, halt/drain/유지/resume |
| source manifest | PASS | 재사용 40 / 수정 4 / 신규 7, 원본 RTL 변경 없음 |

Verilator 5.050에서 assertion을 켜고 실행했고, RV64 프로그램은 xPack GCC 15.2로
`rv64imfc_zicsr_zifencei / lp64f`를 지정해 조립했다. core의 표준 Debug Spec 지원을
테스트한 것이 아니다. CSR interrupt-enable 후 실제 interrupt handler 진입, 표준
JTAG/DTM/DMI, 전체 ISA differential, Linux 부팅, RV32 실행, 성능/STA는 미검증이다.

elaboration의 diagnostic 344개와 Verilator의 기존 frontend width/local-latch 등
경고는 로그에 보존했다. 오류 0을 lint 경고 0 또는 합성 sign-off로 해석하지 않는다.
SRAM/ROM은 전원 초기값이 지정되지 않는다. 이번 boot test는 SRAM_INIT_FILE로 적재했으며
Boot ROM은 사용하지 않았으므로 빈 초기화 경고가 있다.

초기 검증에서 찾아 수정한 문제:

- AXI crossbar 내부의 과거 TIM address decode를 새 공용 1MiB SRAM map으로 바꿨다.
- native halt 동안 frontend가 새 bus fetch를 계속 보내던 경로를 IF adapter에서 막았다.

이 두 수정 뒤 최종 전체 directed suite를 재실행했다. 초기 halt 실패 로그도
`out/initial_boot_halt_failure.log`에 남겼다. 52개 directed check와 짧은 boot smoke는
RVA23 적합성, 임의 workload의 정확성, 멀티코어 coherence를 증명하지 않는다.

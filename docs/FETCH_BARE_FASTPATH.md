# Bare instruction fetch fast path

`rv23_if_translate`에서 non-virtual M-mode 또는 `satp.MODE=0` fetch가
이미 물리 주소인 경우 TLB의 bare 응답과 wrapper의 TRANSLATE 상태를
기다리지 않고 직접 ISSUE한다. PADDR_WIDTH 초과 주소는 기존 instruction
access fault(원인 1)로 반환한다. MMU가 켜진 S/U/guest 요청은 기존 TLB/MMU
경로를 사용한다. TLB에 fast-path 요청을 넣지 않아 orphan 응답이 남지 않는다.

## 현재 측정

같은 저장 2회 RVV CoreMark ELF SHA-256
`ac07f4ffa2b4e087b79893bf43427a53ad9a398fb15b47610c4b00caa0cd1597`:

- burst 기준선: 1,759,805 cycles, IPC 0.313925.
- bare fetch path: 1,639,889 cycles, IPC 0.336881.
- cycle 감소 6.814%; 명령 수 552,447, CRC `[e9f5,e714,1fd7,8e3a]` 동일.

이는 동일한 고정 ELF와 동일한 burst RTL 기준선 간의 Verilator cycle
비교다. 합성 Fmax나 공식 CoreMark 점수가 아니다. 10회 동일 ELF는
실행 중이며, 결과 보고서에 완료되기 전까지 개선 확정 근거로 쓰지 않는다.

검증: `run_if_translation_checks.py`의 실제 응답 ID/epoch, stale epoch,
상위 물리 주소 fault와 bare fast-path 시점 확인; XLEN64 H/V native
integration의 guest Sv39 및 HLV/HSV/HLVX 시나리오; `check_rtl.py`와
source manifest 검사. 전체 ACT/RV32 release sign-off는 별도다.

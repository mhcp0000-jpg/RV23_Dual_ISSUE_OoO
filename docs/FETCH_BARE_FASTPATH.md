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

같은 10회 RVV ELF는 **8,783,204→8,183,137 cycles
(6.832% 감소)**, IPC **0.314474→0.337534**다. 명령 수 2,762,088과
CRC `[e9f5,e714,1fd7,8e3a]`가 동일하다. 2회와 10회 모두 저장 ELF를
그대로 사용했다. 합성 Fmax나 공식 CoreMark 점수가 아니다.

[원시 실행 및 모델·ELF 해시](evidence/fetch_bare_fastpath.json).

검증: `run_if_translation_checks.py`의 실제 응답 ID/epoch, stale epoch,
상위 물리 주소 fault와 bare fast-path 시점 확인; XLEN64 H/V native
integration의 guest Sv39 및 HLV/HSV/HLVX 시나리오; `check_rtl.py`와
source manifest 검사. 전체 ACT/RV32 release sign-off는 별도다.

# Fetch response turnover

`rv23_if_translate`가 성공한 fetch bus 응답을 받는 edge에 다음 요청도
수락할 수 있게 했다. 응답 ID가 현재 요청과 맞고 `RRESP=OKAY`이며
응답이 소비될 때만 다음 요청을 받아들인다. 오류 응답은 기존대로 다음
fetch를 막는다. 새 요청은 bare 경로면 바로 ISSUE, MMU 경로면 기존
TRANSLATE 단계로 들어간다. 가상 주소 변환, AXI 요청 안정성, 응답
ID/epoch 전달은 그대로 둔다.

## 같은 ELF 결과

| RVV CoreMark | Before | After | Cycle 감소 | IPC after |
| --- | ---: | ---: | ---: | ---: |
| 2회 | 1,639,889 | 1,580,346 | 3.631% | 0.349573 |
| 10회 | 8,183,137 | 7,881,323 | 3.688% | 0.350460 |

2회/10회 모두 기존 저장 ELF를 재사용했다. 명령 수와 CoreMark CRC는
같다. 각각 비교한 fast-path baseline보다 추가 cycle 감소다. 수치는
RTL 시뮬레이션이고 물리 Fmax 또는 공식 CoreMark 인증 결과가 아니다.

검증: response-turnover directed TB, IF response ID/stale epoch/fault
ownership, XLEN64 H/V native integration의 VS Sv39 및 HLV/HSV/HLVX,
SystemVerilog elaboration, source manifest.
`docs/evidence/fetch_response_turnover.json`이 실행 로그와 ELF/model의
해시를 묶는다.

아직 하나의 fetch 응답당 다음 요청 하나를 교체 수락하는 구조다. 여러
fetch outstanding, redirect 이후 wrong-path 취소, fetch queue의 추가
대역폭 개선은 남아 있다.

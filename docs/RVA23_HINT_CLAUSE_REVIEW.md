# PAUSE·NTL·PREFETCH 검토 결론

이 문서는 `hints.1` 및 `hints.2` 검토 주제의 결론이다. 전체 RVA23S64
달성이나 일반 memory-order/timing 증명을 선언하지 않는다. 현재 target의
ignored-hint 정책이 필수 architectural 동작을 충족하는지 검토한다.

## 규격과 선택한 구현

- [Zihintntl 1.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zihintntl.html):
  네 NTL 및 C/Zca 압축형을 무시할 수 있다. target memory 명령의
  architectural 효과를 바꾸지 않아야 한다. 현재 코어는 locality 요청을 무시한다.
- [Zihintpause 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zihintpause.html):
  추가 대기 시간이 0일 수 있으며, outstanding memory 완료까지 기다리는
  구현도 설명한다. 현재 코어는 기존 FENCE drain을 사용하고 별도 무기한
  pause 상태나 WFI/WRS wake 조건을 사용하지 않는다.
- [Zicbop 1.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/cmo.html):
  I/R/W prefetch는 HINT이며 실제 cache allocation은 필수가 아니다.
  현재 코어는 prefetch 요청을 무시한다.

## 소스 경로의 논증

| 명령 | 현재 target의 decode/실행 연결 | 판단 |
|---|---|---|
| NTL.P1/PALL/S1/ALL | `rv_decode2`의 OP ADD, rd=x0. `uop_writes_dst_o=(rd!=0)`으로 architectural 목적지를 쓰지 않는다. load/store/CSR/branch 분류는 기본 0이며 다른 확장 override와 인코딩이 겹치지 않는다. `rv_int_alu`의 ADD는 memory request나 FP flag를 생성하지 않는다. | hint 자체의 architectural 상태 변경 및 data-memory 접근 경로가 없다. 다음 memory 명령에 locality state를 전달하지 않아 본래 경로를 유지한다. |
| C.NTL 네 형식 | `rv_c_expander`의 C.ADD rd=x0, rs2=x2~x5가 같은 ADD 경로로 확장된다. 원래 16비트 길이는 frontend/backend에 별도로 유지된다. | 같은 ignored 정책이며 PC는 2바이트 진행한다. rd=x0라는 이유로 illegal 처리하지 않는다. |
| PREFETCH.I/R/W | OP-IMM ORI rd=x0, FU_INT. load/store flag는 0이며 CSR/CBO head의 opcode와 다르다. `rv_int_alu`의 OR 결과는 버린다. | target address의 번역·PMP/PMA·MMIO access를 요청하는 경로가 없으므로 address 자체로 data fault를 생성하지 않는다. 실제 prefetch 성능은 제공하지 않는다. |
| PAUSE | `0x0100000f`, FU_FENCE·serializing, 목적지 없음. `rv_backend.head_is_fence`와 `rv_fence_controller`가 older LSU idle을 기다려 완료한다. FENCE.I가 아니므로 해당 frontend flush를 요청하지 않는다. | 더 강한 drain 정책은 허용된 선택이다. 명령 자체가 새 LSU read/write를 할당하지 않지만 이전 요청은 완료될 수 있다. 외부 memory가 응답하지 않는 시스템 정지는 PAUSE 고유 timeout 보장과 구분한다. |

후속 override를 포함한 `rv_decode2`와 ROB head 분류를 검토했다. integer
hint가 guest memory, CBO, vector 또는 SYSTEM 명령으로 다시 분류되지 않는다.
소스 검토는 아래 runtime snapshot/같은 ELF 대조와 함께 사용한다.

## 실행 근거와 한계

| 검사 | 직접 관련 사례와 parent suite |
|---|---|
| `run_rv64i_hint_contract.py --check` | PAUSE 한 형식과 NTL 네 형식을 포함한 1,132개 RV64I HINT sample. PC+4, GPR/FPR snapshot·FCSR·guard를 검사한다. parent suite 이벤트 168,849개와 대조군 44개다. |
| `run_rvc_hint_contract.py --check` | C.NTL 네 code point를 포함한 395개 base-C HINT/NOP. PC+2와 register/FCSR/guard 보존. parent suite 이벤트 59,261개와 대조군 20개다. |
| `run_prefetch_hint_contract.py --check` | I/R/W의 1,413개 offset/base sample. 동일 ELF Sail/RTL 이벤트 211,068개, GPR/FPR snapshot 값 90,432개 및 대조군 14개. |

parent suite의 모든 사례가 PAUSE/NTL만인 것은 아니다. 세 검사는 현재
RTL/model·ELF·Sail·assembly·trace·로그·helper 해시를 재확인하며 필수 통합
감사에 포함된다. prefetch의 모든 encoding 조합이나 모든 privilege/interrupt
스케줄을 실행한 것으로 확대하지 않는다. data-memory 요청 부재는 runtime
snapshot만의 추론이 아니라 위의 decoder/실행 경로와 결합한 결론이다.

cache replacement·실제 hardware prefetch·전력 감소는 이 ISA HINT의 필수
구현 조건과 구분한다. 고정 cycle latency나 전체 side-channel 보장도 여기서
도출하지 않는다. Zkt/Zvkt는 [별도 timing 근거](TIMING_CONTRACT.md)로 검토한다.

`hints.1`은 현재 활성 target의 decode와 data-memory 경로 검토로,
`hints.2`는 허용된 ignored/drain 정책과 optional 효과·timing 범위의 구분으로
작업 목록에서 닫는다. RTL 변경이나 새로운 실행 완료를 뜻하지 않는다.

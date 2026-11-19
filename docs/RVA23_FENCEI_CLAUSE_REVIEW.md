# Zifencei 2.0 검토 결론

기준은 [Zifencei 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zifencei.html)이다.
현재 단일 hart·write-through D-cache·coherent SRAM snoop의 구현에서
`fencei.1`과 `fencei.2` 검토 주제의 결론을 기록한다.

## 이전 explicit memory와 후속 fetch

`rv_decode2`는 FENCE.I를 serializing으로 분류한다. `rv_backend`의 ROB head
실행이 `rv_fence_controller`를 거치며, LSU `memory_idle_o`가 될 때만 완료한다.
LSU idle은 store buffer empty, outstanding load·direct pending/failed 없음,
translation idle을 함께 요구한다. `rv_store_buffer`는 요청 수락만으로 비우지
않고 drain response에서 done을 세운 뒤 pop한다. D-cache의 write-through
응답도 실제 memory 응답 이후 전달된다. 따라서 retire된 선행 store가 아직
bus 응답을 기다리는 동안 fence가 완료되는 경로가 아니다.

FENCE.I가 ROB head일 때 그보다 앞선 explicit 명령은 완료·retire한 상태다.
older atomic/vector/CBO의 head-owner memory 작업 역시 각 완료 조건을
통과해야 한다. 현재 보수적 drain은 필요한 store뿐 아니라 진행 중인 ordinary
load와 translation도 기다린다. faulted store의 정상 완료로 위장하지 않는다.
실제 SRAM/CLINT 응답·fence retire·후속 요청 순서는 기존 fence-order 검사가
관찰하며, 새 자기수정 코드 검사는 실제 store와 후속 instruction 실행을 연결한다.

## I-cache refill과 frontend의 경계

backend의 `i_fabric_idle_i`는 현재 상수 1이다. 따라서 I-cache가 idle이 될
때까지 기다리는 것으로 설명하면 부정확하다. 실제 보장은 다음 경로다.

1. `rv_ooo_core.fence_i_o`가 정상 FENCE.I retire에서 발생하고 SoC I-cache의
   invalidate에 연결된다. `rv23_cache`는 valid를 지우며 invalidate cycle에
   새 CPU 접근을 받지 않는다.
2. 이미 진행 중인 refill은 `killed_q`로 표시한다. 마지막 beat에서
   `!killed_q && !invalidate_request`일 때만 tag valid를 설치하므로 같은 cycle의
   invalidate도 우선한다. 이미 수락한 bus 작업은 취소하지 않고 완료한다.
3. cache는 오래된 요청에 대한 응답 자체를 반환할 수 있다. IF adapter는
   수락 때 저장한 request id/epoch를 응답에 유지한다. 이것을 새 epoch로
   재표시해 전달하지 않는다.
4. `rv_trap_controller`가 FENCE.I retire 다음 경계에서 sequential PC로
   architectural redirect를 만든다. backend는 pending redirect 동안 younger
   진행을 막고, ROB는 serializing head와 younger 명령을 함께 retire하지 않는다.
5. frontend는 fetch queue/target buffer를 무효화하고 epoch를 바꾼다. 현재
   outstanding id/epoch가 맞는 응답만 queue를 채운다. target-buffer invalidate는
   같은 cycle의 fill보다 우선하므로 늦은 old response가 다시 유효해지지 않는다.

SRAM accepted write의 snoop도 resident I-line을 invalidate하고 겹치는 refill을
죽인다. 그 coherence와 architectural redirect를 함께 검토했다. 이 결론은
다중 hart의 remote instruction synchronization을 구현했다는 뜻이 아니다.

## 무시해야 하는 필드와 새 native 검사

`rv_decode2`, backend head/retire 판별과 core pulse는 opcode/funct3로
FENCE.I를 인식한다. funct12/rs1/rd를 주소·권한·목적지로 사용하지 않는다.
이는 현재 확장에 예약된 세 필드를 무시하는 구현 선택과 일치한다.

`scripts/run_fencei_selfmod_contract.py`는 74개 field sample 각각에 대해
16비트 C.LI 또는 32비트 ADDI를 실제 SRAM store로 1→2 결과로 수정한다.
target FENCE.I 이후 같은 PC를 다시 실행해 새 instruction과 결과를 확인한다.
총 148개 probe, old/new 실행 296건, 같은 ELF Sail/RTL 이벤트 2,968건이
일치했다. fields는 0/전부 1/12개 one-hot funct12와 모든 rd/rs1의 대표 조합이다.
모든 funct12×rd×rs1 조합을 실행한 것은 아니다.

16비트 instruction은 line 내 모든 32개 halfword 위치, 32비트 instruction은
모든 16개 word 위치를 사용한다. 정확한 store 주소/값, PC+2/4와 FENCE.I의
목적지 write 없음을 확인한다. stale instruction과 잘못된 destination write의
trace 대조군 네 개를 거부했다. 이는 FENCE.I를 NOP로 바꾼 RTL 실행은 아니며,
source 경로의 논증을 이 trace 대조군으로 대체하지 않는다.

기존 fetch atomicity 검사는 정렬 word 위치 16개와 debug write/refill 중첩
464건, 마지막 write 이후 FENCE.I 뒤의 새 instruction만 retire하는 조건을
검사한다. 이 component 근거는 `audit_profile_contracts.py`가 현재 source/model/
log 해시와 witness로 재확인한다.

```text
python scripts/run_fencei_selfmod_contract.py --check
python scripts/run_fence_order.py --check
python scripts/audit_profile_contracts.py
python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm
```

새 native 근거는 `out/rva23/fencei_selfmod_contract/report.json`이다.
현재 source·model·ELF·Sail·assembly·trace·log/helper 해시에 연결한다.
`fencei.1`·`fencei.2`를 이 source 검토와 실행 근거로 닫으며 전체 memory model,
임의의 외부 master·fault·interrupt schedule 또는 전체 프로파일 달성을 선언하지 않는다.

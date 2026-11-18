# CMO 1.0 절별 검토

기준은 [CMO 1.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/cmo.html)이다.
현재 단일 hart·write-through L1·공유 SRAM 구조의 동작과 검증 범위를 연결한다.
임의의 다중 hart·외부 비일관성 DMA 환경으로 결과를 확대하지 않는다.

| 조항·계약 | 구현 연결 | 실행 근거와 범위 |
|---|---|---|
| block 형상 | `rv23_pkg`와 cache는 64바이트 block을 사용한다. CBO head는 `[31:6]`으로 block을 정렬한다. | CBO.ZERO의 비정렬 rs1에서 같은 block의 8개 word와 앞뒤 guard를 검사한다. Zic64b 형상 및 기존 component/integration 근거다. |
| CLEAN | `rv_backend`가 ROB head와 `lsu_memory_idle`을 기다린 후 `rv23_cbo_head`를 시작한다. 이전 write-through 응답이 끝났으므로 별도 dirty writeback 없이 완료한다. | 현재 H/V replay 및 permission matrix의 허용된 CLEAN, fence의 외부 응답 순서 검사. 모든 버스 backpressure 스케줄의 증명은 아니다. |
| INVAL / FLUSH | 권한·주소 검사 이후 cache invalidate handshake를 기다린다. clean 상태에서 FLUSH는 invalidate로 완료할 수 있다. | 기존 실제 discard 카운터 및 Svpbmt alias의 flush/refill 검사를 연결한다. NOP decode만으로 통과했다고 간주하지 않는다. |
| ZERO | 주소·번역·block-wide PMP 검사 후 8개 64비트 쓰기를 응답마다 진행한다. 마지막 응답 이후 완료한다. | 기존 CBO 값·guard 검사와 debug 쓰기를 첫/마지막 beat 사이에 넣은 fence-order 검사를 연결한다. block 전체 원자성을 주장하지 않는다. |
| envcfg 권한 | CBIE/CBCFE/CBZE와 M/HS/U/VS/VU 상태를 검사하고 illegal/virtual cause를 선택한다. | `run_cbo_permission_matrix.py`의 255개 조합 중 허용 128건, illegal 96건, virtual 31건이다. 정확한 instruction tval와 trap 이후 메모리 보존을 검사한다. |
| 주소 보호 | pointer mask, translation, PMP 및 PMA 검사 뒤 side effect를 허용한다. management는 read형 번역, ZERO는 write형 번역을 사용하고 fault를 store 계열로 보고한다. | 기존 Sv39 read-only/D-bit 및 precise store-fault 사례, guest pointer-mask/PTE 근거와 연결한다. 모든 stage/PTE/PMP/operation의 Cartesian product는 아니다. |
| PREFETCH.I/R/W | ORI rd=x0의 HINT 공간으로 처리한다. 정수 ALU에서 목적지 write를 억제하며 load/store·CBO/PTW 요청을 생성하는 decode가 아니다. | 아래 native field sweep과 기존 U-mode faulting-address 세 형식 실행. 실제 데이터를 미리 가져오는 기능을 이 근거로 주장하지 않는다. |
| memory ordering | CBO의 head 실행과 메모리 drain, fence 및 coherence 경로를 공유한다. | `run_fence_order.py`의 SRAM/CLINT/atomic 응답 순서, ZERO/debug 중첩 및 scalar/vector 후속 값 검사. 일반 RVWMO 전체 검증은 별도다. |

## Zicbop field sweep

`scripts/run_prefetch_hint_contract.py`는 3형식 각각에 대해 32바이트 배수인
signed offset 128개를 base x0/x8/x31에서 실행하고, 모든 base x0~x31에서
최소·0·최대 offset을 실행한다. 중복을 제외한 1,413개 사례이며 모든
12,288개 raw encoding 조합을 실행한 것은 아니다.

기존의 immutable RV64I HINT snapshot scaffold와 oracle을 재사용한다.
각 명령 전 GPR/FPR 64개가 예상 값인지 확인하고, 명령 후 원본 SD/FSD
snapshot과 LD 결과 64개, FCSR 및 두 guard, PC+4를 검사한다.
base x8은 실제 SRAM buffer이고, x0는 0, 나머지 base는 선택된 상위 비트
패턴이다. 각 배치의 동일 ELF를 Sail 및 전체 H/V RTL에 사용한다.

12개 ELF의 Sail/RTL 이벤트 211,068건이 일치했다. GPR/FPR snapshot 값
90,432개, FCSR 읽기 1,413개 및 guard 읽기 2,826개를 검사했다.
형식별 snapshot 결과를 변조한 trace 대조군 14개를 거부했다.
각 배치의 별도 zero-instruction probe는 cause 2와 정확한 PC/tval를 검사한다.

이 테스트는 M-mode Bare에서 현재 ignored-hint 정책의 architectural 상태를
검사한다. 실행 중 bus transaction을 관찰하는 wrapper는 사용하지 않으므로,
trace 일치만으로 MMIO 부작용 부재를 증명했다고 하지 않는다. 해당 연결은
정수 decode 경로의 source review와 구분한다. 모든 권한·페이지·PMP 상태,
실제 prefetch 성능·cache 정책 및 모든 ordering 스케줄을 포괄하지 않는다.

```text
python scripts/run_prefetch_hint_contract.py --check
python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm
```

각 배치의 assembly·ELF·reference·현재 RTL/model·trace·로그와 snapshot helper
해시를 확인한다. 전체 RVA23S64 규격 조항 감사는 여전히 진행 중이다.

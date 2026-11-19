# Cache line refill burst

I/D 캐시 미스의 64바이트 라인 리필을 AXI64 단일 요청 8회에서
**ARLEN=7 / ARSIZE=3 / INCR 한 번**으로 변경했다. 스칼라와 벡터가
공유하는 D-cache 경로에 동일하게 적용한다. 캐시의 두 64비트 뱅크,
태그와 히트 경로는 유지한다.

## 구현

`rv23_cache.refill_o`가 실제 라인 리필을 구분한다.
`rv_local_to_axi_bridge.CACHE_BURST`는 기본 0이며 SoC의 I/D 브리지에서만
1로 설정한다. SRAM 영역 내 64바이트 정렬, 8바이트 read, 비-device
요청만 burst로 보낸다. MMIO와 uncached 접근, write-through store,
직접 CBO 트랜잭션은 기존 경로를 사용한다.

브리지의 임시 8×64비트 버퍼는 도착한 beat를 캐시의 순차 word 요청에
전달한다. 전체 라인이 도착할 때까지 기다렸다가 복사하지 않는다.
별도 데이터 캐시나 prefetcher가 아니며 동시에 처리하는 refill은 하나다.
여러 독립 miss를 동시에 처리하는 MSHR/MO는 이번 변경에 포함하지 않는다.
버퍼 payload를 reset하지 않고 valid와 제어 상태만 reset한다.

RRESP 오류, ID 불일치, 이른/늦은 RLAST, 응답 timeout은 라인 리필 오류로
돌려준다. 이미 받아들인 AXI 전송은 마지막 beat까지 drain하며, AR가
stall된 경우 timeout 후에도 ARVALID와 payload를 유지한다. 늦은 응답을
다음 요청의 데이터로 사용하지 않는다. SoC의 debug halt/CBO 준비 조건도
I/D 브리지 idle을 포함하므로 아직 drain 중인 전송을 완료로 표시하지 않는다.
리필 도중 invalidate/snoop이 발생하면 기존 캐시의 killed-fill 처리를 유지한다.

## 완료된 국소 측정

`python scripts/run_cache_burst.py`는 동일 TB에서 burst off/on을 비교한다.

| 경로 | Before cycles | After cycles | 감소 |
| --- | ---: | ---: | ---: |
| 지연·오류 주입 AXI target, cold line 하나 | 55 | 36 | 34.55% |
| 실제 양쪽 AXI bridge + 동기 SRAM, cold line 32개 | 1,952 | 1,344 | 31.15% |

32개 라인의 AR 수는 256→32, 데이터 beat는 양쪽 모두 256이다.
이 수치는 TB 호출·응답 대기를 포함하며 전체 CoreMark나 물리 Fmax 수치가 아니다.
실제 SRAM은 committed write-through로 초기화하고 이후 256개 resident word와
resident write snoop를 확인한다. 별도 오류 주입 시험은 모든 beat 위치의
RRESP 오류, 잘못된 ID, 조기/지연 RLAST, AR/R timeout과 late drain,
리필 중 invalidate/snoop, 응답 backpressure, MMIO 비할당을 포함한다.

전체 코어의 M/HS/VS H/V 메모리 및 guest 공유 D-cache directed 실행도 통과했다.
기존 캐시 fault/bank 시험 4,648 checks도 통과했다. 전체 ACT/RV32 release나
현재 burst RTL의 Linux 부팅 완료를 의미하지 않는다.

EEW8/16/32 × full/short VL × cold/warm의 12개 native vector PLIC 경계도
통과했다. 최종 RF 기록→retire→trap, 이후 scalar store의 가시성과
핸들러의 모든 active byte 확인을 포함한다. 128바이트 cold load의
관측 리필 주소 요청 수는 2회이며 warm load는 0회다.

동일한 저장 ELF의 2회/10회 CoreMark 비교는 실행 중이며, 완료 후 별도
source-bound snapshot에 기록한다. 코드 변경의 국소 효과를 전체 CoreMark
개선율로 대신 표시하지 않는다.

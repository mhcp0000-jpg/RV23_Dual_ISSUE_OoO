# A 2.1 절별 검토

기준은 [A 2.1](https://docs.riscv.org/reference/isa/v20260120/unpriv/a-st-ext.html)이다.
현재 단일 hart와 shared SRAM의 atomic 경로, native 실행 및 독립 값 모델을 연결한다.
유한한 데이터·순서·간섭 검사를 일반 다중 hart RVWMO 증명으로 확대하지 않는다.

| 조항·계약 | 구현 연결 | 실행 근거와 한계 |
|---|---|---|
| 12.1.1 aq/rl | atomic은 ROB head에서 시작하며 기존 LSU 메모리 처리를 drain한다. 후속 메모리도 head 소유권 및 완료를 따른다. 현재 구현은 unordered 연산에도 보수적인 순서를 사용한다. | 새 field matrix는 18 AMO 형식 각각의 네 aq/rl 인코딩에서 결과를 검사한다. 순서 근거는 별도 `run_fence_order.py`의 응답·retire·후속 요청 관찰이며, field 값 검사만으로 acquire/release를 증명하지 않는다. |
| 12.1.2 LR.W/D 결과 | `rv23_atomic_head`가 번역·보호를 검사하고 `rv23_atomic_engine`이 exclusive read를 수행한다. LR.W는 old word를 XLEN으로 부호 확장한다. | 기존 AMO/LRSC audit의 W 결과와 compressed constrained LR/SC의 W/D byte oracle 및 같은 ELF Sail 대조를 연결한다. |
| 12.1.2 SC 성공/실패 | 성공은 memory write 및 status 0, 실패는 비영 status와 memory 보존을 반환한다. exclusive monitor는 SC 시 소비된다. | 기존 W audit 및 W/D constrained loop의 성공과 강제 no-LR 실패, debug write 중첩의 성공/실패·재사용 실패 검사를 연결한다. 이 구현의 failure code 1에만 의존하는 portable software를 요구하지 않는다. |
| reservation 범위·간섭 | SRAM monitor가 64바이트 line 범위를 추적하며 address/size도 확인한다. debug AXI write의 snoop가 monitor를 무효화한다. | `run_wrs_debug_wake.py`의 W/D LR→debug write→SC와 추가 SC 실패, 인접 line 보존. 모든 가능한 간섭 시점·master를 포괄하지 않는다. |
| 정렬·주소 보호 | atomic head가 자연 정렬, 번역, PMP/PMA를 확인한 후 요청한다. 비정렬 atomic을 일반 LSU assist로 분해하지 않는다. | 기존 atomic/atomic_sv39 H/V replay, protection/fault 사례 및 ACT A·privileged 근거를 연결한다. 모든 operation×PTE×PMP×guest 조합은 아니다. |
| 12.1.3 constrained 진행성 | head owner·exclusive 버스 경로와 공정한 요청/응답 처리를 사용한다. | 일반 loop 72 placements·1,152 updates와 compressed loop 144 placements·2,304 updates. 두 compressed shape의 명령 수와 retry 배치를 검사한다. 지속적인 외부 간섭 및 공정성의 보편적 liveness 증명은 아니다. |
| 12.1.4 AMO.W/D | swap/add/logic/signed·unsigned min/max는 memory old 값을 반환하고 폭에 맞는 새 값을 저장한다. W는 상위 operand 비트를 무시하고 반환값을 부호 확장한다. | 아래 18형식 field matrix와 기존 upstream 42 AMO retirement의 값 모델. rd=x0에서도 메모리 갱신을 후속 읽기로 관찰한다. |
| 레지스터 중첩 | 주소와 operand는 writeback 이전의 source 상태에서 취한다. | distinct, rd=x0, rd=rs2, rd=rs1, rs1=rs2, triple alias의 여섯 패턴. prime register의 대표 조합이며 모든 32개 register의 Cartesian product는 아니다. |

## Exclusive retry 경로의 검토 결론

`atomics.1`은 accepted write가 read-modify-write 사이에 들어와도 AMO가 그
값을 잃지 않는 경로의 검토다. [A의 AMO 규칙](https://docs.riscv.org/reference/isa/unpriv/a-st-ext.html)은
원래 값을 반환하고 그 값과 operand로 계산한 결과를 원자적으로 저장하도록
요구한다. 현재 SRAM 플랫폼은 exclusive read/write와 내부 재시도로 구현한다.

`rv_backend`는 ROB head의 atomic을 LSU drain 뒤 `rv23_atomic_head`로 보낸다.
`rv23_soc_top`의 production engine은 data AXI mux를 거쳐 system xbar와 SRAM
bridge에 연결된다. 이 integration 연결과 aq/rl 전후 drain 실행은 기존 native
AMO field matrix 및 `run_fence_order.py`의 별도 근거를 함께 사용한다.

`rv23_atomic_engine`은 read의 old 값과 연산 결과를 보관하되 EXOKAY write
응답을 받아야 그 old 값을 완료 결과로 내보낸다. write가 OKAY로 실패하면
RESULT로 가지 않고 READ_ADDR부터 다시 읽고 계산한다. SLVERR/DECERR와 ID
오류는 store access fault 경로이며 성공 또는 정상 재시도로 숨기지 않는다.

`rv_axi_to_local_bridge`는 확장된 AXI ID별 monitor를 유지한다. 수락된 local
write는 같은 64바이트 granule의 monitor를 무효화한다. exclusive AW에서는
주소·크기와 monitor를 확인하고 그 예약을 소비한다. 실패한 exclusive W는
OKAY 응답으로 끝내고 SRAM local write 요청을 만들지 않는다. 성공 AW 뒤에는
해당 target bridge가 transaction을 소유하므로 그 local write까지 다른 master의
write가 끼어들지 않는다. 따라서 read 뒤 같은 granule의 write가 먼저 수락됐으면
실패·재읽기하고, 성공 write의 SRAM 수락 시점에는 그 사이의 다른 write를 잃지
않는다. SRAM write snoop는 resident cache 값에도 전달된다. 이 논증은 현재
단일 target bridge의 직렬화 및 모든 SRAM master가 그 경로를 쓴다는 조건이다.

새 `rv23_amo_retry_matrix_tb`는 production engine·xbar·exclusive bridge·SRAM을
그대로 연결한다. 기본 wiring·bus task·SV arithmetic oracle은 기존 atomic
engine bench에서 가져왔으며, 독립 Python byte/정수 oracle도 결과를 재계산한다.
test-only AW backpressure adapter로 engine의 exclusive write를 잠시 막아 다른
master의 실제 read/write 완료가 exclusive read와 write 사이에 오게 한다.
engine·bridge의 response/monitor를 강제로 바꾸거나 합성 응답을 주입하지 않는다.
adapter는 기존 production mux/cache/ROB를 포함하는 whole-core 검사는 아니다.

9개 AMO × D/W-low/W-high × 다섯 간섭 형태 × 한 번/두 번의 270개 사례를
실행했다. 간섭 형태는 같은 word 전체 쓰기, 대상 byte 쓰기, 같은 line의 다른
word 쓰기, 다른 line 쓰기 및 read-only master다. 같은 granule의 162개 사례에서
exclusive 실패 243회를 만들고 매번 재읽은 최신 old 값 및 최종 memory 값을
확인했다. 다른 line과 read-only는 각각 54개 사례에서 불필요한 재시도가 없었다.
같은 line의 다른 word 및 다른 line의 간섭 값도 완료 뒤 108회 다시 읽어 확인했다.

초기화 쓰기를 제외한 SRAM write snoop 594회는 간섭 write 324회와 성공 AMO
270회다. 각 사례에서 이 수를 확인해 실패 exclusive 243회가 write를 새지 않도록
검사했다. 반환값·최종 word는 두 word lane과 이웃 byte 보존을 포함한다.
read 횟수·실패 응답 횟수·실제 write 수·old·memory의 변조 대조군 다섯 개를
거부했고, 현재 RTL/TB·model binary·build/run 로그·driver 해시를 `--check`로
재검사한다. 보고서는 `out/rva23/amo_retry_matrix/report.json`이다.

이 source 논증·실제 component 간섭 실행·기존 whole-core 값/순서 근거로
`atomics.1`을 닫는다. 모든 오류/위임/PMP 조합, cache/debug/interrupt의 모든
interleaving, 지속 간섭 아래 진행성이나 전체 RVWMO 증명을 뜻하지 않는다.
fault 우선순위 `atomics.2`와 constrained progress `atomics.3`은 계속 열린다.

## AMO field matrix 실행

`scripts/run_amo_field_contract.py`는 18형식 × aq/rl 네 조합 × alias 여섯 패턴
× 선택 old/operand 네 쌍인 1,728개 사례를 현재 전체 H/V SoC에서 실행한다.
M-mode Bare SRAM 접근이며, W/D 자연 정렬 주소를 64바이트 line 내에서 바꾼다.
각 ELF를 변경하지 않고 Sail과 RTL에 사용한다.

독립 모델은 ELF의 file-backed 바이트 및 실제 initializer store로 memory를
구성한다. 반환 old 값, 정수 규칙에 따른 memory 갱신과 후속 guard load를
검사하며, 모든 대상 AMO write의 모든 바이트가 관찰돼야 한다.
영 초기화 SRAM을 가정하지 않는다. 원본 instruction 및 다음 PC+4도 검사한다.
형식별 atomic 결과 또는 memory 관찰값을 변조한 trace 대조군을 사용한다.

7개 ELF에서 Sail/RTL 이벤트 67,538건이 일치했다. 비영 목적지 결과 1,440개를
독립 계산했고, 목적지 x0 288건을 포함한 AMO write 1,728건의 전 바이트를
후속 guard 읽기 6,912건에서 관찰했다. 변조 대조군 44개를 거부했다.
모든 형식에서 네 aq/rl 인코딩을 실행했지만, 이 값 검사를 순서 증명으로
해석하지 않는다. 결과는 `out/rva23/amo_field_contract/report.json`에 있다.

```text
python scripts/run_amo_field_contract.py --check
python scripts/run_amo_retry_matrix.py --check
python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm
```

현재 RTL/model·Sail·assembly·ELF·trace·로그와 독립 helper의 해시를 재검사한다.
전체 입력·예약 인코딩·fault·privilege·동시성 스케줄 및 전체 프로파일 감사는 별도다.

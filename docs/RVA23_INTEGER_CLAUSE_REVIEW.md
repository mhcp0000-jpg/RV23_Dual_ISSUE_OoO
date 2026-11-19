# RVA23S64의 기본 정수 I/M 절별 검토

기준은 [RV32I 2.1](https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html),
[RV64I 2.1](https://docs.riscv.org/reference/isa/v20260120/unpriv/rv64.html) 및
[M 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/m-st-ext.html)이다.
RV64I는 RV32I의 설명을 상속하므로 RV64 추가 명령만으로 기본 ISA를 검토하지 않는다.
아래는 현재 RTL 경로와 유한 실행 근거의 연결이다. 공유 특권·메모리·OoO 상태의
전체 조합이나 전체 RVA23 완료를 판정하지 않는다.

## 기본 I와 RV64 차이

| 절·계약 | 확인한 경로 | 실행 근거와 남은 범위 |
|---|---|---|
| RV32I 1.1.1 / RV64I 3.1.1 상태 | XLEN=64 decoder/operand/ALU/branch/PRF 경로. rd=x0는 architectural destination 쓰기에서 제외하고 source x0는 0을 사용한다. | current H/V 모델의 RV64I/M 및 register-field/C/HINT 실행. HINT의 모든 GPR/FPR snapshot과 같은 값 self-write 허용. 물리 PRF·rename의 모든 가능한 OoO 배치를 뜻하지 않는다. |
| RV32I 1.1.2~3 형식·즉시값 | `rv_decode2`의 I/S/B/U/J immediate 생성과 rd/rs field를 실제 retire 인코딩에서 별도로 계산한다. | `audit_rv64i_compute_control.py`: 38개 연산 형식의 target 1,475건, setup 포함 6,252건. 압축 확장은 [별도 C 검토](RVA23_C_CLAUSE_REVIEW.md)로 구분한다. |
| RV32I 1.1.4 / RV64I 3.1.2 계산 | XLEN 연산과 W의 low 32-bit/sign extension을 구분한다. RV64 immediate shift는 6비트, W/register W shift는 5비트 경로를 사용한다. LUI의 32비트 부호 확장과 AUIPC의 PC 상대 계산을 확인한다. | 위 38형식의 독립 정수·PC 계산 및 결과/target 변조 38개. 각 ISA 입력의 직교 조합이나 타이밍 sign-off는 아니다. reserved W shift 공간과 다른 확장이 정의한 인코딩을 일괄 illegal로 확대하지 않는다. |
| RV32I 1.1.5 제어 이전 | `rv_branch_unit`이 signed/unsigned 조건을 구분하고 JALR bit 0을 제거한다. backend가 원래 instruction length의 2/4바이트를 link/순차 PC에 전달한다. | 기존 JAL/JALR·여섯 조건부 branch의 값/다음 PC 및 양쪽 branch 결과, 추가 compressed control 3,042건의 halfword PC·odd pointer·x1 alias. 모든 fault/interrupt와 target 조합은 공유 privileged/fetch 검토다. |
| RV32I 1.1.6 / RV64I 3.1.3 메모리 | `rv_lsu_pipe`/LSQ와 head assist가 주소·크기·부호·byte mask 및 RV64 LD/SD/LWU를 처리한다. 데이터 주소의 유효 범위와 PMA는 플랫폼 계약으로 분리한다. | `audit_rv64i_memory_values.py`: 기존 14개 ELF의 memory retire 1,591건과 ELF-backed byte model. 파일에 없고 아직 쓰지 않은 SRAM 바이트를 0으로 가정하지 않으며 읽지 않은 store 바이트까지 검증했다고 하지 않는다. Zicclsm의 정렬/분할/fault 및 공유 scalar/vector 순서 근거를 함께 사용한다. |
| RV32I 1.1.7 FENCE | decoder는 FENCE의 rd/rs1을 목적지 쓰기로 사용하지 않는다. 현재 core는 store/LSU/atomic 상태를 직렬화하는 보수적 실행을 사용한다. | `run_fence_order.py`의 네 FENCE 인코딩과 여섯 SRAM/CLINT 조합에서 선행 응답→retire→후속 요청을 실제 계측. FENCE.TSO를 더 강하게 실행하는 동작도 포함한다. 외부 master와 모든 memory-model litmus의 증명은 아니다. FENCE.I는 별도 Zifencei 계약이다. |
| RV32I 1.1.8 환경 호출·breakpoint | SYSTEM decode와 precise trap/CSR/return 경로를 사용한다. 원래 PC·명령 길이와 fault context를 전달한다. | M/HS/U/VS/VU ECALL은 permission matrix의 실제 복귀 흐름, EBREAK/C.EBREAK는 88개 breakpoint/illegal/FS-Off context-form의 EPC/tval/GVA/delegation 검사에 연결한다. 전체 S/H privileged chapter를 이로 대체하지 않는다. |
| RV32I 1.1.9 / RV64I 3.1.4 HINT | rd=x0 계산 또는 null-set FENCE로 inert 동작. NTL/PAUSE 및 semihost 표식은 기능·ABI와 구분한다. | `run_rv64i_hint_contract.py`: 31개 기본 연산군·36분류, 선택 사례 1,132개와 GPR/FPR snapshot 72,448개, FCSR/guard. 현재 정책의 custom HINT도 포함한다. 전체 HINT 공간을 열거하거나 semihost 서비스를 구현한 근거는 아니다. |

기본 I 감사의 trap·FENCE·메모리 ordering 범위를 산술 감사의 38형식으로
확대하지 않는다. CSR 접근과 S/H 권한·WARL은 Zicsr/privileged 계약에 연결한다.

## M의 곱셈·나눗셈

| 절 | 확인한 구현·값 계약 | 근거와 범위 |
|---|---|---|
| 11.1.1 곱셈 | `rv_multiplier`는 2×XLEN product와 연산별 signedness를 사용하고 low/high를 선택한다. MULW는 low 32-bit 결과를 sign extend한다. | `audit_rv64m_contract.py`의 Python 무한 정밀 정수 곱셈과 MUL/MULH/MULHU/MULHSU/MULW retire 값 비교. high/low 연속 명령의 fusion은 필수 기능으로 요구하지 않는다. |
| 11.1.2 나눗셈 | `rv_divider`는 word 입력을 signedness에 맞춰 32비트로 제한하고 몫·나머지의 부호를 보정한다. 0 divisor와 signed minimum/-1의 fast result를 따로 선택한다. | DIV/DIVU/REM/REMU 및 W형식을 독립 정수 계산한다. 0 divisor의 몫/나머지, signed overflow와 W 부호 확장 사례가 실제 포함된다. 정수 divide-by-zero에 arithmetic trap을 요구하지 않는다. |
| 11.1.3 Zmmul | full M의 곱셈 부분집합에 해당한다. | full M의 13형식 target 값 296개와 변조 대조군 13개가 통과했다. M 구현을 Zmmul만 구현한 것으로 축소하지 않는다. |

13개 M 형식은 같은 ELF의 Sail/RTL 이벤트 비교와 독립 수치 검사로 연결된다.
모든 피연산자 조합·owner flush 및 모든 병렬 WB 스케줄을 이 296개로 증명하지 않는다.
현재 MUL/DIV pipeline 지연은 별도 측정과 README에 기록하며 ISA 기능 완료와
물리 STA/Fmax 또는 divider 성능 목표를 혼동하지 않는다.

## M 인코딩과 목적지 x0의 검토 결론

`muldiv.1`은 현재 RV64 full-M target의 인코딩과 x0 disposition 검토다.
`rv_decode2`는 OP/funct7=1의 여덟 funct3를 MUL/MULH/MULHSU/MULHU 및
DIV/DIVU/REM/REMU로, OP-32/funct7=1은 MULW와 네 DIV/REM W 형식으로
분류한다. OP-32의 funct3=1/2/3은 현재 target에서 illegal이다. 관련 B/MOP/H/V
override는 이 세 인코딩을 합법화하지 않는다. 다른 opcode나 향후 확장의
reserved 공간 전체에 illegal trap을 강제한다는 뜻은 아니다.

두 M decode 경로 모두 `rd!=0`일 때만 destination을 쓴다. illegal cleanup은
FU/port·load/store/CSR/branch/fence 분류와 destination write를 없애고 cause 2와
원본 instruction tval를 ROB 예외 경로에 전달한다. 예약 형식을 잘못 MUL/DIV에
보내거나 rd=x0라는 이유로 예약 instruction을 NOP로 바꾸지 않는지 검토했다.

`scripts/run_rv64m_encoding_edges.py`는 13형식 각각의 x0 목적지에 0/0,
signed minimum64/-1, word minimum32/-1, all-ones/0 및 큰 비트 패턴/7을
사용한 65개 비트랩 사례를 실행한다. 정수 divide-by-zero·overflow는 FP flag나
arithmetic trap을 만들지 않아야 한다. 값 결과 자체는 목적지 x0라 관찰하지
않으며 기존 296개 비영 목적지 수치 검사와 구분한다.

예약 OP-32 세 형식은 rd=x0/x1/x31과 네 source-field 조합으로 36개를 실행했다.
cause 2·정확한 PC·원본 tval·writeback 없음과 trap 후 PC+4 복귀를 확인했다.
전체 101개 사례에서 source 두 개·ra·x31·FCSR 관찰값 505개가 보존됐으며,
동일 ELF의 Sail/RTL 이벤트 3,910건이 일치했다. 잘못된 cause/tval·x0 write·
source 값의 trace 대조군 네 개를 거부했다. 보고서는
`out/rva23/rv64m_encoding_edges/report.json`이며 현재 RTL/model·ELF·Sail·
assembly·trace·로그와 generator/helper 해시를 재검사한다.

이 source 검토와 실행 근거로 `muldiv.1`을 닫는다. 모든 register/operand
조합이나 동시 WB·인터럽트·flush 스케줄을 이 encoding 검사로 증명하지 않는다.

## M issue·취소·retire 소유권의 검토 결론

`rv_backend`는 multiplier 요청에 operation/word, ROB sequence와 physical
destination valid/tag를 같은 issue 경계에서 전달한다. DIV tag pipeline도
이 metadata를 한 묶음으로 저장하며, flush된 slot은 execute valid를 내지 않는다.
MUL의 두 stage와 DIV의 busy/result slot은 owner metadata를 data와 함께 유지하고
wrap-aware sequence 비교로 younger/full flush를 처리한다. ready가 낮으면
result valid와 data·sequence·destination metadata를 유지한다.

두 producer의 결과는 각각 writeback source 2/3으로 연결된다. arbiter는
live ROB owner가 없거나 flush 범위에 들어가는 결과를 버리고, 살아 있는 결과만
physical destination write와 ROB complete로 전달한다. ROB는 resident entry의
valid와 sequence가 일치해야 complete를 받는다. integer PRF의 speculative
write와 architectural mapping의 retire commit은 구분한다. rename의 committed
mapping은 retire_fire와 해당 destination으로 갱신하며, in-order ROB retire가
architectural 결과의 순서를 정한다.

기존 standalone multiplier/divider unit bench의 flush는 0에 고정돼 있으므로
이를 active-kill 증거로 사용하지 않았다. 새 `rv64_muldiv_ownership_tb`는 실제
production 모듈을 XLEN64로 인스턴스화한다. MUL stage0 또는 DIV busy가 실제로
활성인 시점과, result가 ready를 기다리는 시점에서 flush를 넣는다.
full/word data path, sequence 250↔2 wrap, boundary equality 및 flush-all의
20개 시나리오에서 younger 12개 취소·older/equal 8개 보존·취소 후 새 tag로
12회 재사용을 확인했다. 결과 24개의 sequence/valid를 각각 네 대기 경계에서
검사하고 유효 목적지가 있는 결과는 data/physical tag도 검사했다.
destination-valid=0 요청 네 개도 포함했다. flush cycle의 새 요청은
ready=0이어야 한다. witness 누락 대조군 네 개를 검사기가 거부했다.

`scripts/run_rv64_muldiv_ownership.py --check`는 bench/RTL·model binary·build/run
로그 해시를 재확인한다. 실제 production RV64 issue/execute/retire 연결은 기존
`audit_rv64_ooo_integration.py`의 pipeline CSV와 64비트 결과 10개, dual
issue/execute/retire 각 네 회 및 younger bypass 여섯 회와 함께 사용한다.
component에서 본 active kill을 production branch/interrupt의 모든 스케줄을
실행한 것처럼 확대하지 않는다. 이 source 연결과 component/native 근거로
`muldiv.2`를 닫으며 전체 프로파일 및 물리 timing 판정은 별도다.

## 기본 동기 예외의 검토 결론

`base.1`은 [RV32I 환경 호출·breakpoint 조항](https://docs.riscv.org/reference/isa/unpriv/rv32.html)과
[privileged 환경 호출·breakpoint 규칙](https://docs.riscv.org/reference/isa/priv/machine.html),
[H 위임 규칙](https://docs.riscv.org/reference/isa/priv/hypervisor.html)을 실제 경로에 연결한다.
ECALL은 U/VU=8, HS=9, VS=10, M=11 원인으로 예외를 만들며 EBREAK와
C.EBREAK는 cause 3이다. EPC는 해당 명령 자신의 주소이고, 동기 예외 명령은
retire되지 않아 `instret`를 증가시키지 않는다. illegal cause 2의 instruction
tval 제공 및 breakpoint의 PC tval은 이 target이 선택한 정보 제공 정책이다.
예약 공간 전체가 항상 illegal이라는 주장은 하지 않는다.

`rv_decode2`는 ECALL을 serializing SYSTEM으로, EBREAK를 원본 PC를 가진
decode 예외로 분류한다. C.EBREAK의 압축 확장 경로도 원래 16비트 instruction과
PC를 보존한다. 정의된 illegal cleanup은 destination/FU/메모리 부작용을 없애고
원본 instruction을 cause 2의 tval로 전달한다. ECALL은 `rv_backend`의 head
completion에서 current privilege와 virtualization에 따라 cause를 선택하고
기본 tval=0을 사용한다. `rv_rob`의 head 예외는 정상 retire 대신 trap 경로로
전달되며, backend는 `rob_trap_valid` 동안 retire_fire를 억제한다. CSR의
`minstret` 증가는 이 retire_fire 합계로 결정된다.

`rv_trap_controller`는 ROB의 PC/cause/tval을 CSR에 전달하고 수락된 trap의
vector로 redirect한다. `rv_csr_file`은 M에서 아래로 위임하지 않으며 medeleg를
적용한다. `rv_hypervisor_csrs`는 V=1인 경우 hedeleg를 추가 적용한다.
hedeleg의 ECALL 9/10/11 비트는 read-only zero라 VS ECALL이 VS로 재위임되지
않는다. EPC를 다음 명령으로 바꾸는 것은 handler 소프트웨어의 책임이며,
하드웨어가 ECALL/EBREAK의 길이를 더해 trap EPC를 만들지 않는다.

새 `scripts/run_base_trap_contract.py`는 M/HS/U/VS/VU × medeleg/hedeleg의
네 설정 × ECALL/EBREAK/C.EBREAK/illegal32(0xffffffff)/illegal16(0)의
100개 사례를 실행한다. 대상 handler는 M 60·HS 31·VS 9건이다. 각 handler가
cause/EPC/tval을 확인하고 EPC를 원래 길이의 다음 명령으로 설정해 복귀한다.
복귀 후 sentinel 증가와 별도 M escape trap을 확인하며, 두 보존 레지스터의
관찰값 200개와 probe/escape trap 200개를 독립 검사한다.

각 probe 바로 앞 `instret` 읽기와 handler 첫 명령의 읽기를 비교하면 차이는
첫 CSR 읽기의 retire에 해당하는 1이어야 한다. RTL과 Sail 각각의 100쌍에서
이를 확인했다. RTL boot와 ELF부터 시작하는 Sail은 절대 카운터 원점이 다르므로
이 두 CSR 읽기의 절대값만 정규화한 뒤 동일 ELF 이벤트 8,083건을 비교한다.
차이 자체와 계산 결과는 정규화하지 않는다. cause/tval/destination/handler/
instret/보존 값의 잘못된 trace 대조군 여섯 개를 검사기가 거부했다.

현재 모델·RTL·ELF·assembly·Sail·trace·로그 해시는 `--check`로 재검사한다.
기존 88개 breakpoint/illegal/FS-Off context-form의 GVA/MPV/SPV/SPVP·위임·
복귀 검사를 함께 사용해 `base.1`을 닫는다. 새 100개가 모든 불법 인코딩,
동시 외부 interrupt/debug 요청 또는 모든 memory fault 우선순위를 검사한 것은
아니다. 메모리 원자성·RVWMO 검토 `base.2`와 전체 프로파일 판정은 계속 열린다.

## 앞선 store가 늦어지는 경우의 load 값·대기 검사

`base.2`의 [RVWMO load-value axiom](https://docs.riscv.org/reference/isa/unpriv/rvwmo.html)
검토를 보강한다. 같은 hart의 앞선 store가 아직 외부 메모리에 쓰이지 않았어도
후속 load에는 해당 바이트의 최신 값이 필요하다. store buffer forwarding으로
이를 만족할 수 있으므로 이 값을 확인하는 것과 모든 접근의 외부 완료 순서를
강제하는 것은 구분한다. 전체 RVWMO의 global order·atomicity·progress 검토를
이 단일 hart 값 검사로 대체하지 않는다.

`scripts/run_delayed_store_order.py`는 DIV 의존성으로 앞선 store의 주소 또는
데이터 준비를 늦춘다. SB/SH/SW/SD와 LB/LH/LW/LD/LBU/LHU/LWU, line 내
0/8/48/56 위치 및 word의 앞/뒤 load 위치를 조합한 M-mode Bare SRAM 사례
448개를 실행한다. 8바이트 load의 두 위치 선택은 같은 주소이며 distinct
encoding 448개를 주장하지 않는다. 초기화 후 FENCE와 warm load를 수행하지만
지연시킨 store와 대상 load 사이에는 FENCE를 넣지 않는다.

Python byte model은 명시적으로 초기화한 8바이트에 store의 하위 바이트만
덮어 쓴 뒤 load 폭·부호 확장을 계산한다. 대상 load 448개 및 전체 word guard
448개, 합계 896개 결과를 검사해 각 대상 store의 전 바이트와 건드리지 않은
바이트를 관찰한다. 0으로 초기화된 SRAM을 가정하지 않는다. 같은 ELF를 Sail,
기존 전체 H/V RTL 모델 및 관찰 wrapper 모델에서 실행해 각 RTL trace의
Sail 이벤트 21,290건이 일치해야 한다. probe/guard 결과 변조 두 개를 거부한다.

`rv23_delayed_store_order_tb`는 production `rv_lsq`의 candidate와 stall 신호를
관찰한다. ELF 실행 이후의 유효 candidate만 집계하며 unknown-address,
partial-overlap, store-data 대기 중에는 load request/forward/candidate-valid가
나오면 실패한다. DIV busy와 동시에 더 오래된 unresolved SQ entry가 있는
load 대기도 wrap-aware sequence 차이로 확인한다. 각각의 대기 witness와
DIV 겹침 witness가 실제로 있어야 하며 누락 대조군 다섯 개를 거부한다.
계수는 lane-cycle 누적이고 CoreMark의 원인별 stall 비율이나 개별 사례 전체의
대기 보장을 뜻하지 않는다. 보고서는 `out/rva23/delayed_store_order/report.json`이다.

현재 실행에서 unknown-address 14,172·partial-overlap 8,175·store-data 6,488
lane-cycle을 관찰했다. unknown-address 대기와 DIV busy의 겹침 13,436건 모두
더 오래된 unresolved SQ entry가 존재했다. 후보 lane별 누적이므로 동시 두
lane을 하나의 elapsed cycle로 합치거나 CoreMark 성능 수치로 사용하지 않는다.

이 검사는 메모리 disambiguation·partial overlap의 현재 유한 실행 근거다.
MMIO·PMA/PMP/주소 번역·misaligned·다중 master·벡터·fault/flush 조합 및
자연 정렬 transfer의 외부 관찰 원자성은 기존 관련 검사와 별도 검토가 필요하다.
`base.2`는 계속 열린 상태다.

## 재검사와 전체 목표

- `python scripts/audit_rv64i_compute_control.py`
- `python scripts/audit_rv64i_memory_values.py`
- `python scripts/audit_rv64m_contract.py`
- `python scripts/run_rv64m_encoding_edges.py --check`
- `python scripts/run_rv64_muldiv_ownership.py --check`
- `python scripts/run_base_trap_contract.py --check`
- `python scripts/run_delayed_store_order.py --check`
- `python scripts/run_rv64i_hint_contract.py --check`
- `python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm`

각 감사는 현재 소스·모델·ELF·참조 모델·trace·로그의 해시와 연결한다.
FENCE/fetch 원자성·H/S/VM·스칼라/벡터 순서·RV32 보존·Linux의 공유 근거는
전체 요구사항 감사에서 함께 확인한다. 이 표의 존재나 개별 PASS로 전체
RVA23S64 규격 조항 검토 또는 공식 인증을 완료했다고 판정하지 않는다.

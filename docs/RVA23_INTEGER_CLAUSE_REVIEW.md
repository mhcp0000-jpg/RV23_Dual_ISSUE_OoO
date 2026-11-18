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

## 재검사와 전체 목표

- `python scripts/audit_rv64i_compute_control.py`
- `python scripts/audit_rv64i_memory_values.py`
- `python scripts/audit_rv64m_contract.py`
- `python scripts/run_rv64i_hint_contract.py --check`
- `python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm`

각 감사는 현재 소스·모델·ELF·참조 모델·trace·로그의 해시와 연결한다.
FENCE/fetch 원자성·H/S/VM·스칼라/벡터 순서·RV32 보존·Linux의 공유 근거는
전체 요구사항 감사에서 함께 확인한다. 이 표의 존재나 개별 PASS로 전체
RVA23S64 규격 조항 검토 또는 공식 인증을 완료했다고 판정하지 않는다.

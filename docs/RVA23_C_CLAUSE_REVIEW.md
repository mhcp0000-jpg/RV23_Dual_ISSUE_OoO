# RVA23S64의 C 2.0 절별 검토

기준은 [C 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/c-st-ext.html)이다.
이 표는 RV64+D 구성에서 C 고유 인코딩·실행 경로를 절별로 대조한다.
기본 I/D/A 및 S/H/MMU의 모든 공유 조항이나 전체 RVA23 완료를 판정하는 표는 아니다.
실행 수치는 현재 RTL에 묶인 유한 검증 근거이며 형식 전체의 입력 직교 조합이나
보편적 liveness 증명을 뜻하지 않는다.

| C 절 | 확인한 구현·실행 연결 | 현재 근거와 범위 |
|---|---|---|
| 27.1.1 개요 | `rv_decode2`는 `rv_c_expander`를 각 lane에 연결한다. backend는 원래 명령 길이를 ROB에 보존하고 branch 경로에 2/4바이트를 전달한다. RV64의 ADDIW/LD/SD와 D의 압축 FP 메모리를 선택한다. | native control 3,042개, mixed 16/32-bit 및 halfword PC 실행, LR/SC의 32-bit LR·SC IF 라인 교차. 명령 주소·이전 권한·fetch fault의 전체 조합은 공유 특권/fetch 검토에 남는다. |
| 27.1.2 형식 | expander의 prime/full 레지스터 필드와 즉시값 배선을 독립 필드 계산 및 실제 결과와 대조한다. | compute 7,226개와 memory 2,448개. 모든 산술 즉시값/shift 및 메모리 offset 값에 선택 데이터/레지스터를 조합한다. expander의 65,536개 설정 비교를 독립 전체 legality oracle로 간주하지 않는다. |
| 27.1.3 load/store | 정수 W/D 8형식과 FP D 4형식이 같은 LSU·commit 경로에 연결된다. FP f0는 유효하며 정수 SP load rd=x0와 구분한다. | memory 12형식, store 1,224건 전 바이트 관찰, 정수 base/data 중첩 242건, 비정렬/라인/Bare 물리 페이지 경계. C FP의 FS-Off 예외는 기존 11개 특권/delegation context의 breakpoint metadata matrix와 연결한다. 변환 fault/권한의 모든 동시 조합은 공유 LSU/MMU/FP 검토다. |
| 27.1.4 제어 이전 | C.J/BEQZ/BNEZ의 부호 확장 및 C.JR/JALR의 bit 0 제거, JALR의 PC+2 링크를 확인한다. RV32 전용 C.JAL은 RV64 목표에 추가하지 않는다. | native 5형식 3,042개. signed boundary/bit offsets, branch true/false, odd indirect pointer 248개, source/destination x1 alias 8개. 모든 offset·trap·interrupt 직교 조합은 별도다. |
| 27.1.5 계산·NOP·예외 | RV64 word 연산은 low 32-bit를 sign extend한다. NOP/HINT와 명시적 영 illegal, C.EBREAK를 구분하고 원래 길이·trap 값을 보존한다. | compute 18형식 7,226개, HINT/NOP 395개, 영 illegal의 양쪽 halfword phase와 PC+2 복귀 4회. C.EBREAK cause/EPC/tval/GVA/delegation은 기존 `run_hypervisor_breakpoint_metadata.py`에서 M/HS/U/VS/VU context로 실행한다. |
| 27.1.6 LR/SC 내 사용 | 허용된 I 연산의 압축형을 LR/SC의 같은 reservation/atomic owner 경로에서 실행한다. 실제 ELF의 4/16명령·12/36바이트와 retry 목적지를 검사한다. | native 144개 W/D placement, 성공 2,304회. LR 없는 SC 사전 실패 144회를 분리해 compressed retry도 실행한다. 외부 master 공정성·보편적 진행성은 A/플랫폼 공유 검토이며 이 유한 실행으로 증명하지 않는다. |
| 27.1.7 HINT | rd=x0 또는 self-write의 inert 경로를 사용한다. NTL 네 형식을 포함하고 custom-designated shift 공간에서도 현재 구현의 inert 정책을 검사한다. | 394개 코드 포인트 전부와 NOP. GPR/FPR snapshot 25,280개, FCSR 및 SRAM guard 보존. 각 HINT가 한 번 retire하며 backend의 공통 `retire_count_i`가 CSR counter로 전달되고 `mcountinhibit.IR`에 따라 instret에 반영된다. 모든 CSR/권한 조합이나 미세구조 효과의 측정은 아니다. |
| 27.1.8 opcode 목록 | RV64+D 목록에 해당하는 형식을 위 실행 근거와 연결한다. 추가 Zcb/Zcmop의 합법 공간은 별도 확장으로 구분한다. | reserved 표기를 모두 영구 illegal로 확대하지 않는다. 영 인코딩은 명시적 illegal로 검사하며 Zcb/Zcmop 실행 근거는 `profile_scalar/instructions`의 현재 H/V replay와 압축 확장 GNU vectors에 있다. |

## 재현과 근거 연결

다음 생성기는 현재 전체 H/V 모델과 Sail에 배치별 같은 ELF를 사용한다.
`--check`는 재컴파일 없이 assembly·실행 artifact·현재 모델/RTL·helper 해시 및
독립 결과 검사를 반복한다.

- `scripts/run_rv64c_compute_contract.py --check`
- `scripts/run_rv64c_control_contract.py --check`
- `scripts/run_rv64c_memory_contract.py --check`
- `scripts/run_compressed_lrsc_contract.py --check`
- `scripts/run_rvc_hint_contract.py --check`

기존 `rv64uc/rvc`의 별도 직접 계산은 `scripts/audit_rv64c_contract.py`다.
현재 소스의 C.EBREAK/FS-Off context는 `scripts/audit_profile_contracts.py`가
보관 ELF·trace·로그 및 실행 report와 연결한다.
전체 근거 감사 명령은 다음과 같다.

```text
python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm
```

이 표에서 공유 검토로 남긴 예외·상태·순서 항목을 전체 프로파일 체크리스트에서
제거하지 않는다. ACT 통과나 이 표의 존재만으로 전체 RVA23S64 완료를 선언하지 않는다.

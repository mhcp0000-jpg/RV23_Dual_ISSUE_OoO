# Zicsr 2.0의 명령 의미와 공유 CSR 계약

기준은 [Zicsr 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zicsr.html)이다.
CSR 명령의 읽기·쓰기 의미를 각 CSR bank의 존재·권한·WARL·자동 갱신 규칙과
구분한다. 모든 CSR 주소나 공유 특권 조항을 세 CSR의 실행만으로 검증하지 않는다.

| 절·계약 | 구현 연결 | 확인한 근거와 범위 |
|---|---|---|
| 5.1.1 주소·operand | decoder의 12비트 CSR 주소와 5비트 unsigned immediate가 CSR request로 전달된다. register형은 원래 source 값을 사용한다. | mscratch/minstret/mhartid의 6형식 378개. immediate 0/1/15/16/31 및 선택 full-XLEN register 값과 rd/rs1 중첩을 실행한다. 나머지 CSR bank의 존재·WARL은 별도다. |
| CSRRW/CSRRWI | 기존 CSR 값을 rd에 반환하고 원래 operand로 쓴다. rd=x0는 architectural 결과를 쓰지 않으며 rs1=x0 또는 uimm=0이어도 write intent는 있다. | 반환값·후속 readback 및 read-only CSR의 쓰기 예외. 표준 CSR에는 read side effect가 없어 내부 combinational read strobe의 억제를 직접 측정한 근거는 아니다. custom read-side-effect CSR은 구현 범위에 추가하지 않는다. |
| CSRRS/CSRRC | source mask로 set/clear한다. write intent는 데이터가 아니라 인코딩의 zero register로 결정한다. | backend가 `rob_head_instruction[19:15] == 0`을 `csr_rs1_is_zero_i`에 전달하고 `rv_csr_file`이 이를 사용한다. encoded nonzero register의 값 0인 RS/RC 36건을 실행한다. |
| CSRRSI/CSRRCI | uimm=0에서 write를 억제하고 다른 값에서는 unsigned 5비트 mask를 사용한다. rd=x0도 이 규칙을 바꾸지 않는다. | uimm의 zero/top-bit/max 값, ignored destination 및 read-only 접근 조합. |
| 원자적 RMW·rd/rs1 alias | pending CSR write는 head의 commit에 연결되며 원래 source와 기존 CSR 값을 구분한다. | rd=rs1 72건의 이전 값과 후속 CSR 값을 검사한다. read-only 예외 114건에서 destination writeback이 없고 cause/EPC/tval이 정확하다. |
| per-field/whole-CSR side effect | `csr_write_intent`는 encoded-zero 규칙을 따른다. 어떤 필드가 실제 쓰기에서 변하는지는 해당 CSR bank가 결정한다. | plain RW scratch, read-only ID, 자기 갱신 instret의 세 종류를 확인한다. custom field side effect, PMP WARL의 모든 RMW 조합 및 mip의 software/external-wire 혼합은 이 테스트로 증명하지 않는다. |
| 자기 갱신 CSR의 explicit write | `minstret_incremented`와 explicit write 선택 경로를 분리한다. explicit write가 해당 CSR 명령의 자동 증가보다 우선한다. | 독립 retirement 모델의 read 212건/write 242건. 인접 write/read/read의 0x1234→0x1234→0x1235를 ELF와 실행에서 확인한다. |
| 5.1.1.1 같은 hart의 순서 | CSR pending/ROB head와 serializing 경로를 사용해 기존 값과 갱신 뒤 readback을 프로그램 순서로 관찰한다. | 같은 ELF의 Sail/RTL 이벤트 9,182건 및 readback. 모든 CSR 간접 효과·trap/interrupt interleave의 조합은 아니다. |
| 다른 hart/device와의 순서 | 현재 SoC는 단일 hart다. CSR과 일반 memory 사이의 관계를 무조건 full fence라고 간주하지 않는다. | 실제 memory/IO 순서는 `run_fence_order.py`의 별도 request/response/retire 계측을 사용한다. multi-hart/device 전체 CSR ordering proof는 아니다. |

## 공유 근거와 재현

- `python scripts/run_zicsr_rmw_contract.py --check`는 생성 assembly, 현재 RTL/model,
  같은 ELF·Sail·trace·로그와 독립 검사 helper의 해시 및 결과를 다시 검사한다.
- 기존 `run_counter_permission_matrix.py`의 M/HS/VS/U/VU permission 조합,
  `run_profile_csr_geometry.py`의 CSR geometry/WARL,
  `run_fp_permission_matrix.py`의 FCSR/FRM/FFLAGS 접근·Dirty,
  `audit_profile_contracts.py`의 H/S 상태·counter·trap 근거를 함께 사용한다.
- `python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm`
  명령이 이 실행과 현재 공유 근거를 연결한다.

프로그램 oracle은 `minstret`를 통제된 값으로 쓴 뒤 시작하며, ELF 진입 이전
fixture 실행과 CSR 초기값 차이를 명령 의미의 불일치로 취급하지 않는다.
각 trap의 원래 명령과 PC는 프로그램 영역에서 별도로 검사한다.

이 표는 CSR 명령 의미와 공유 CSR 구현의 연결을 기록한다. 전체 S/H CSR bank,
권한·WARL·예외 조항 및 전체 RVA23S64 완료 판정은 구현 체크리스트에 남겨 둔다.

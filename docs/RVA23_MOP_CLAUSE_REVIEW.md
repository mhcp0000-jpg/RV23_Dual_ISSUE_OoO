# Zimop/Zcmop 1.0 절별 검토

기준은 [Zimop/Zcmop 1.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zimop.html)이다.
이 검토는 의미를 재정의하는 확장이 없는 현재 코어의 기본 MOP 동작을 다룬다.
reference의 Zicfilp/Zicfiss도 비활성이며, 이 기능을 구현했다고 광고하지 않는다.

| 조항·계약 | 구현 연결 | 근거와 범위 |
|---|---|---|
| 9.1 MOP.R 32형식 | `rv_decode2`의 Zimop override가 SYSTEM/FUNCT3=4의 정의된 number 필드를 인식하고 integer zero-result 연산으로 연결한다. | 전 32형식·모든 목적지 x0~x31과 별도/중첩 source. 비영 목적지가 0으로 바뀌며 다른 source 값은 보존된다. |
| 9.1 MOP.RR 8형식 | 같은 기본 zero-result 경로를 사용하며 추가 rs2 필드를 구분한다. | 전 8형식·모든 목적지와 rd=rs1, rd=rs2, triple alias 및 별도 source. 전체 source Cartesian product를 실행한 것은 아니다. |
| HINT와의 구분 | R/RR는 목적지 상태를 바꿀 수 있어 기본 HINT의 inert 동작과 구분한다. rd=x0는 무시된다. | M 3,072개·U 288개에서 destination/source alias 1,848건과 rd=x0 192건. 각 비영 목적지를 사전에 비영 값으로 채워 NOP 구현과 구분한다. |
| 비특권 명령 | default MOP override는 `uop_is_csr`와 serializing을 해제한다. SYSTEM opcode라는 이유로 CSR 권한 검사에 넘기지 않는다. | U mode에서 전 40형식의 선택 사례가 실행되며, 마지막 ECALL cause 8과 정확한 PC를 검사한다. 모든 H/VS/VU state 조합의 실행 근거는 아니다. |
| syntactic dependency | 현재 default path는 `uop_src_used=0`과 `REG_NONE` source를 사용한다. 실제 source를 소비해야 하는 재정의된 명령으로 간주하지 않는다. | source-level 연결을 확인한다. source 값이 서로 다른 유한 실행 및 alias 결과를 검사했으나 보편적인 RVWMO dependency/다른 hart 관찰 증명은 아니다. |
| 9.1.1 Zcmop 8형식 | `rv_c_expander`의 정의된 C.LUI odd-register/zero-immediate 공간을 inert 명령으로 확장한다. | 전 8개 코드 포인트, full GPR/FPR snapshot 512개·FCSR·guard와 PC+2. C.MOP를 R/RR처럼 xn=0으로 쓰지 않는지 확인한다. |
| 이후 확장의 재정의 | 확장이 이 공간을 다른 의미로 사용할 수 있다는 점을 기본 동작과 구분한다. | shadow-stack/landing-pad 등 재정의된 기능이나 추가 CSR 상태의 동작을 이 결과로 검증했다고 하지 않는다. |

## 실행·재검사

`scripts/run_mop_contract.py`는 8개 ELF에서 총 3,368개 probe를 실행하며,
각 배치의 ELF를 바꾸지 않고 Sail과 native 전체 H/V RTL에 사용한다.
Sail/RTL 이벤트 51,165건과 독립 zero-result/source/FCSR 및 compressed snapshot
검사가 일치했다. trace 변조 대조군 92개를 검사기가 거부했다. 변경 RTL 실행은 아니다.

```text
python scripts/run_mop_contract.py --check
python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm
```

현재 RTL/model, Sail·ELF·assembly·trace·로그 및 immutable snapshot helper의
해시를 확인한다. mandatory extension의 기본 의미와 현재 실행 범위를 연결한
근거이며, 이 표의 존재로 전체 RVA23S64 규격 조항 감사나 인증을 완료하지 않는다.

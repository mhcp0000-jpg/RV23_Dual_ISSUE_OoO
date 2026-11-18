# B 1.0 / Zicond 1.0 절별 검토

기준은 [B의 Zba/Zbb/Zbs](https://docs.riscv.org/reference/isa/v20260120/unpriv/b-st-ext.html)와
[Zicond](https://docs.riscv.org/reference/isa/v20260120/unpriv/zicond.html)다.
RV64 필수 B의 40형식 및 Zicond 두 형식의 구현·기존 실행 근거를 연결한다.
Zbc나 crypto용 Zbk 계열 전체 지원을 이 표로 주장하지 않는다.

| 그룹·계약 | 검토한 형식 | 구현·독립 값 검사 |
|---|---|---|
| Zba 8형식 | ADD.UW, SH1/2/3ADD, SH1/2/3ADD.UW, SLLI.UW | `decode_bitmanip`의 `.uw` 구분과 ALU의 unsigned-word source. 하위 32비트를 zero-extend한 후 XLEN 연산으로 계산하며 일반 word sign-extension과 구분한다. |
| Zbb 논리 3형식 | ANDN, ORN, XNOR | 반전하는 operand와 XLEN mask를 독립 정수 모델로 검사한다. |
| Zbb count 6형식 | CLZ/CTZ/CPOP 및 W형 | W는 상위 32비트를 무시한다. 0의 CLZ/CTZ는 폭 32/64를 반환하며 population count도 선택 폭으로 계산한다. |
| Zbb min/max 4형식 | MIN/MINU/MAX/MAXU | signed와 unsigned 비교를 분리한다. |
| Zbb 확장 3형식 | SEXT.B, SEXT.H, ZEXT.H | 선택 byte/halfword의 부호 또는 zero extension을 확인한다. |
| Zbb rotate 6형식 | ROL/ROLW/ROR/RORW/RORI/RORIW | 32/64비트 순환과 shift mask, W 결과의 sign-extension을 독립 비트열 모델로 계산한다. |
| Zbb byte 2형식 | ORC.B, REV8 | byte별 OR-combine 및 전체 XLEN byte 순서 반전을 확인한다. |
| Zbs 8형식 | BCLR/BCLRI/BEXT/BEXTI/BINV/BINVI/BSET/BSETI | mask된 bit index와 register/immediate 형식, extract의 0/1 결과를 독립 계산한다. |
| Zicond 2형식 | CZERO.EQZ, CZERO.NEZ | rs2의 zero/nonzero에 따라 zero 또는 rs1을 선택한다. 둘 다 실제 source로 decode/issue되며 결과는 일반 integer WB/retire 경로를 사용한다. |

`rv_ooo_pkg.decode_bitmanip`이 형식·immediate·word 동작을 선택하고,
`rv_int_alu`가 계산한다. 두 source를 갖는 Zicond의 의존성 연결은 source-level
검토와 유한 실행을 구분한다. Zkt의 데이터 독립 지연은 별도
[timing 계약](TIMING_CONTRACT.md) 근거이며, 값 검사만으로 timing을 증명하지 않는다.

## 현재 실행 근거

`scripts/audit_rv64b_contract.py`는 기존 같은 ELF 42개의 Sail/전체 H/V RTL
trace를 대조하고 실제 선행 integer writeback으로 source 값을 복원한다.
대상 retirement 1,810개 중 x0 destination 31개는 결과 관찰에서 제외하고,
나머지 1,779개를 독립 계산했다. 형식별 결과 변조 대조군 42개를 거부했다.

별도 native H/V `scalar/bitmanip` replay의 결과 246개도 같은 독립 규칙으로
검사한다. 이는 CLZW/CTZW/CPOPW에서 비영 상위 32비트와 0 입력을 보완한다.
이 supplement를 추가 Sail 대조로 표시하지 않는다. 압축 Zcb의 관련 연산은
[별도 검토](RVA23_ZCB_CLAUSE_REVIEW.md)의 1,008 legal encodings/2,300 probes다.

```text
python scripts/audit_rv64b_contract.py
python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm
```

`out/rva23/rv64b_contract_audit.json`은 현재 model/RTL·ELF·reference·trace·로그와
oracle/helper 해시를 연결한다. 이번 표 추가가 새로운 RTL 실행을 뜻하지 않는다.
모든 입력·register alias·reserved encoding·privilege·flush/stall 조합과
RVWMO syntactic dependency의 보편적 관찰 증명은 이 유한 근거 밖이다.

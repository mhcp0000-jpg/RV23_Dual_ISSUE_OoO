# V 1.0 상태·실행 계약 검토

기준은 [V 1.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/v-st-ext.html)이다.
현재 VLEN128/ELEN64·RV64 H/V 구성의 근거를 조항별로 연결한다.
이 표는 모든 V 명령·합법 operand 조합·스케줄의 검증 완료표가 아니다.
특히 scalar FP 권한 matrix를 vector FP의 권한 검사로 대신하지 않는다.

| 조항·계약 | 구현 연결 | 현재 실행 근거와 범위 |
|---|---|---|
| 30.1.2 parameter | vector PRF·engine의 VLEN128/ELEN64와 CSR vlenb=16 | vector state/config 및 ACT의 동일 DUT 구성. 더 큰 VLEN/ELEN 구성의 sign-off는 아니다. |
| 30.1.3 register/CSR state | `rv_vector_decode_pkg`, `rv_vector_engine`, CSR bank가 vl/vtype/vstart/vcsr를 연결한다. | state differential의 22 configurations·7,040 vector words·770 CSR values, config contract 928개 및 transition 13개. |
| vtype / vill / AVL | vset 경로가 SEW/LMUL·reserved vtype과 AVL을 처리한다. | config contract 및 upstream vset/illegal 사례. 모든 CSR·privilege·page 조합으로 확대하지 않는다. |
| VS/FS 및 guest context | backend가 host/guest 상태에서 vector와 vector-FP 접근을 구분한다. | 아래 다섯 모드 권한 matrix가 각 gate의 Off/on 조합과 Initial/Clean/Dirty를 실행한다. 서로 다른 비영 상태를 네 필드에 섞는 전체 Cartesian product와 모든 opcode는 별도다. |
| 30.1.4 register layout | SEW/LMUL과 element index가 vector register group 위치를 선택한다. | state differential, whole-register move 및 overlap 사례. 모든 source/destination register 조합은 아니다. |
| mask / tail / prestart | element-active와 vstart/vl가 실행·flag 누적을 제어한다. undisturbed 상태는 기존 destination을 보존한다. | agnostic differential 66개·21,120 words는 허용값 집합으로 검사한다. 아래 공유 FP 검사는 tu/mu에서 정확한 비활성 byte 보존을 검사한다. |
| 30.1.7 memory | vector memory engine이 원소마다 번역·PMP/PMA와 commit/head 소유권을 확인한다. | unit/stride/index/segment/whole-register 및 Sv39/guest restart 사례, scalar/vector shared-SRAM 및 ordered MMIO 관찰. 모든 접근 모드×PTE×fault 위치는 아니다. |
| fixed-point state | vxrm과 vxsat를 vector integer 경로에 전달하고 saturation을 누적한다. | fixed-point contract 392개·destination elements 1,568개. 비활성 원소의 saturation 억제와 sticky 상태 포함. |
| 30.1.13 FP state | scalar/vector가 frm과 fflags를 공유한다. vector FP는 유효 원소의 flags만 누적한다. | 아래 공유 state 검사 및 기존 vector FP differential 40 checkpoints. 이 두 검사로 모든 FP instruction family를 검증했다고 하지 않는다. |
| FP 연산·변환 및 Zvfhmin | vector FP lane/convert 경로가 S/D 연산과 필수 half 변환을 처리한다. | lane/integer/engine component oracle, native FP engine 및 ACT generated vector suites. full half 산술의 근거는 아니다. |
| integer/reduction/mask/permutation | vector decoder/engine의 해당 family 및 register group 경로를 사용한다. | native integer engine·scalar/whole moves·Zvbb와 ACT generated vector 2,301 ELF/15 suites. 현재 suite 통과를 각 조항의 모든 operand·reserved 공간 증명으로 확대하지 않는다. |
| 30.1.17 exception/restart | head engine의 부분 완료·fault metadata·vstart와 precise trap/return 경로를 사용한다. | indexed Svade repair/retry, guest segment/FOF 및 whole-register fault 사례, vector/PLIC interrupt 경계 관찰. 모든 trap/delegation·간섭 스케줄은 아니다. |

## Host/guest FS·VS 권한과 Dirty

`scripts/run_vector_permission_matrix.py`는 M/HS/VS/U/VU에서 VFADD.VV,
VADD.VV, VLENB CSR read를 실행한다. host FS·VS와 guest FS·VS의 모든
Off/on gate 패턴을 nonzero=Initial/Clean/Dirty 각각으로 반복하고 중복을
제외한 46개 context를 사용한다. 모드별 138개, 총 690개 probe다.
네 필드에 서로 다른 nonzero 상태를 섞는 모든 4⁴ 조합을 실행한 것은 아니다.

V=0에서는 guest FS/VS가 일반 vector 접근을 제한하지 않아야 한다.
V=1의 vector FP는 host/guest FS와 VS가 모두 활성일 때만 허용된다.
integer vector와 vector CSR 접근은 FS=Off여도 VS가 활성이라면 허용된다.
거부된 명령은 cause 2·정확한 PC·원본 instruction tval·writeback 없음으로
확인한다. cause 22로 바꾸는 동작과 구분한다.

벡터 목적지는 probe 전에 비영 sentinel로 채운다. 허용된 FP는 sNaN 연산으로
NV를 추가하며 host FS/VS 및 V=1 guest FS/VS의 Dirty와 SD를 확인한다.
허용된 integer 연산은 vector Dirty를 확인한다. read-only VLENB는 imprecise
Dirty가 허용되므로 Clean 유지 여부를 강제하지 않는다. 거부된 명령은
vector destination·integer destination·FCSR를 보존해야 한다.

5개 ELF에서 Sail/RTL 이벤트 62,815건이 일치했다. 허용 234건·거부 456건과
ECALL을 포함한 precise trap 1,146건을 확인했다. 이후 데이터 관찰 2,760개,
host Dirty readback 138개 및 guest Dirty readback 30개를 검사했다.
허용/거부의 세 명령 class에서 관찰값을 바꾼 대조군 30개를 거부했다.
결과는 `out/rva23/vector_permission_matrix/report.json`에 기록한다.

이 검사는 Bare·단일 hart이며 모든 opcode, delegation, page/PMP fault와
FS/VS의 결합, fault priority 및 interrupt/flush 스케줄을 대신하지 않는다.

```text
python scripts/run_vector_permission_matrix.py --check
```

## 스칼라와 벡터가 공유하는 FP 상태

`scripts/run_scalar_vector_fp_state.py`는 SEW32/64, LMUL2, 다섯 frm과
VFADD/VFDIV, 여덟 선택 상태를 조합한 160개 사례다. 선택 상태는 전체 활성,
mask로 element 0 제외, vstart=1, VL=1 tail, VL=0, vstart=VL,
mask 전부 0, 마지막 element만 실행하는 vstart=3이다.

각 사례는 scalar FADD → vector FP → scalar FDIV 순서로 실행한다.
scalar FADD는 현재 frm에서 NX를 발생시키며 초기 OF를 보존한다. vector의
sNaN·overflow·0/0·1/0·inexact·subnormal/2 입력은 활성 원소에 한해 계산한다.
후속 scalar FDIV는 DZ를 추가하며 앞선 vector flags를 보존해야 한다.
vector FP 뒤 vstart=0, vcsr=5와 frm 보존을 확인한다.

S/D 각 ELF를 바꾸지 않고 Sail과 production H/V RTL에 사용했다.
이벤트 13,507건이 일치했고, scalar/CSR/후속 memory 관찰값 1,600개를
검사했다. 그중 vector snapshot은 64비트 word 640개다. 실제 활성 원소는
240개이며, 전체 32바이트 destination의 비활성·tail 부분도 확인한다.
예상값은 호스트 float 대신 `fp_reference.BinaryFP`의 정확한 유리수 모델을
사용한다. flags·scalar 결과·vstart·vcsr·관찰 memory 변조 대조군 14개를 거부했다.
이 대조군은 변경 RTL 실행이 아니다.

```text
python scripts/run_scalar_vector_fp_state.py --check
python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm
```

`out/rva23/scalar_vector_fp_state/report.json`과 배치별 보고서는 현재
RTL/model·Sail·assembly·ELF·trace·로그·oracle/helper 해시를 연결한다.
이 검사는 M-mode FS/VS-enabled 상태의 공유 FP contract이며, 모든 벡터
명령이나 FP/VS 권한, fault·interrupt·분기 복구의 모든 조합을 포괄하지 않는다.
나머지 조항의 세부 실행·예외·상태·순서 검토는 계속 진행한다.

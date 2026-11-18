# F/D/Zfhmin/Zfa 절별 검토

기준은 [F 2.2](https://docs.riscv.org/reference/isa/v20260120/unpriv/f-st-ext.html),
[D 2.2](https://docs.riscv.org/reference/isa/v20260120/unpriv/d-st-ext.html),
[Zfhmin 1.0](https://docs.riscv.org/reference/isa/unpriv/zfh.html),
[Zfa 1.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zfa.html)이다.
현재 RV64 FLEN64 H/V SoC의 구현·실행 근거를 연결한다. Q와 full Zfh 산술,
RV32 전용 명령을 필수 기능으로 광고하지 않는다. 각 행의 근거는 유한 실행이며
모든 피연산자·스케줄의 증명 또는 전체 프로파일 인증은 아니다.

| 조항·계약 | 구현 연결 | 실행 근거와 범위 |
|---|---|---|
| F register state, D register width | 별도 FP PRF와 rename/ROB/WB 경로가 32개 architectural FPR과 FLEN64 값을 관리한다. | FP bit/memory suite와 HINT의 32개 FPR snapshot. 단순 feature bit 존재를 실행 근거로 대체하지 않는다. |
| FCSR/FRM/FFLAGS | `rv_csr_file`의 공유 `frm_q`·`fflags_q`가 세 CSR alias를 제공한다. 쓰기는 각 필드 폭에 한정된다. | 아래 six-form alias matrix. 기존 permission matrix의 FS-Off 및 guest FS 검사와 별개다. |
| static/dynamic rounding | decode의 rounding-used 및 `rv_fpu_rva23`의 rm/frm 선택이 format/convert 경로로 전달된다. | arithmetic·integer·format·Zfa suite에서 다섯 static/dynamic mode. 예약 rm의 illegal trap은 현재 정책이며, 예약 의미 자체를 표준 연산으로 정의하지 않는다. |
| accrued exceptions | ROB retire에서 flags를 CSR에 OR 누적한다. FP exception flag 자체로 trap을 요구하지 않는다. | arithmetic 2,700개에서 NV/DZ/OF/UF/NX 발생 및 누적. 비교·변환·memory/bit suite가 flag 추가/보존을 구분한다. |
| NaN 및 subnormal | format/convert 경로가 canonical NaN, signaling 입력 및 gradual underflow를 처리한다. | arithmetic·conversion의 정확한 유리수 모델, NaN·최소 subnormal·normal 경계·underflow/tie 데이터. 모든 IEEE 입력 조합을 실행한 것은 아니다. |
| D의 NaN boxing | S/H 결과의 상위 비트를 1로 채우며 좁은 연산 입력의 boxing을 확인한다. raw transfer는 원본 하위 비트를 사용한다. | bit 1,110개·compare 1,215개·format 1,600개 및 memory 688개에 malformed boxing, payload와 flags 검사. |
| F/D load/store | FP LSU·assist·cache와 압축 D expander를 사용한다. | memory suite 12형식·688개, FP store 320건 전 바이트 관찰. 비정렬 432건·line 경계 208건·Bare 물리 페이지 경계 80건. 압축 nonzero offset은 별도 C-memory 2,448개 suite와 연결한다. |
| arithmetic / FMA | HardFloat add/mul/FMA와 iterative div/sqrt, owner/tag 및 flush 경로를 사용한다. | 18형식·2,700개. exact-rational/정수 sqrt oracle, single-rounding FMA witness 및 결과/flag/split-rounding 변조 대조군 110개. |
| integer conversions | W/WU/L/LU selector와 S/D format 변환, RV64 word 결과 확장을 처리한다. | 16형식·2,760개, signed/unsigned 경계·포화·NaN 및 정수 precision tie, 변조 대조군 48개. |
| FP format conversions | S/D/H 사이 직접 변환하며 목적지에서 한 번 반올림한다. | 6형식·1,600개. 직접 D→H와 S를 거친 이중 반올림을 구분하는 witness, 변조 대조군 31개. |
| sign injection / raw moves / class | `rv_fpu_rva23`와 format의 bit 경로 및 정수/FP destination 선택을 사용한다. | 12형식·1,110개, class 10종·signed zero·NaN payload와 W raw 이동의 sign extension. |
| comparisons / min/max | unbox 이후 비교와 min/max 선택, ROB flag 누적을 사용한다. | 10형식·1,215개. FEQ와 FLT/FLE의 qNaN/sNaN NV 차이, ±0, FMIN/FMAX의 one/two-NaN 결과. |
| Zfhmin | FLH/FSH·half raw moves와 H↔S/D 변환 경로를 제공한다. | memory/format suite에 포함. half add/mul/FMA 등 full Zfh 구현의 근거로 확대하지 않는다. |
| Zfa | FLI·MINM/MAXM·ROUND/ROUNDNX·quiet compare·FCVTMOD 경로를 제공한다. | RV64 필수 S/D 15형식·1,447개, 같은 ELF Sail/RTL 이벤트 32,781건 및 대조군 45개. 선택 operand 범위다. |
| FS/SD 및 virtualization | FP 접근 허용은 host와 V=1 guest FS를 함께 확인한다. 실제 상태 변경은 관련 Dirty를 반영한다. | permission matrix 880개, 허용 594/거부 286·정확한 trap 1,166개. host Dirty 324/guest Dirty 108 readback. 모든 delegation/page/PMP 조합은 아니다. |
| precise state / branch recovery | ROB commit으로 FPR/flags를 반영하며 취소 owner의 결과 valid를 차단한다. | state audit 7 precise traps, branch-order 8개 대표 명령 및 실제 slow FDIV kill witness. 모든 interrupt/flush/stall 스케줄의 증명은 아니다. |

## FCSR alias matrix

`scripts/run_fcsr_alias_contract.py`는 CSR 세 개 × 여섯 CSR 명령의
대표 입력과 FCSR 전체 256개 low-byte 값, 선택 상위 비트를 조합한다.
총 1,664개 probe이며, register form은 값이 0이어도 encoded rs1=x9를 사용한다.
immediate form은 zimm=0~31을 포함한다. 별도의 Zicsr RMW suite가 x0 source,
destination/source alias 및 read-only trap을 검사한다.

각 probe는 CSR의 이전 값을 반환하고, 이어서 FFLAGS/FRM/FCSR 세 alias를
읽어 반영된 field와 상위 비트 마스크를 확인한다. 다른 field 보존도 확인한다.
FFLAGS 쓰기 전 FRM=5, FRM 쓰기 전 FFLAGS=21로 미리 채워, 상대 field를
잘못 0으로 지우는 구현과 구분한다. 대상 field는 0 또는 전부 1에서 시작한다.
현재 확장이 사용하지 않는 FCSR 상위 비트는 read-as-zero/write-ignored다.
예약 frm=5/6/7은 저장·readback하며 해당 상태에서 FP 산술을 실행하지 않는다.
예약 rounding mode 실행의 의미를 이 검사에서 새로 정하지 않는다.

7개 ELF의 Sail/RTL 이벤트 24,109건이 일치했고, 이전 값·세 alias 결과
6,656개를 검사했다. 잘못된 결과를 넣은 trace 대조군 96개를 거부했다.

각 배치의 동일 ELF를 Sail 및 production H/V RTL에서 실행한다. M-mode에서
FS를 활성화한 상태이며, arithmetic flags accrual·FS 권한·guest 상태·pipeline
경합은 위의 별도 검사와 연결한다. 이 matrix만으로 검증했다고 주장하지 않는다.

```text
python scripts/run_fcsr_alias_contract.py --check
python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm
```

기존 각 suite의 명령·관찰 값·대조군 및 재검사 범위는
[상세 계약 검토](RVA23_PROFILE_CONTRACT_REVIEW.md)에 있다. ELF·trace·로그·현재
RTL/model·Sail·generator/helper의 해시가 맞는 근거만 통합 감사가 수용한다.

# RV23 Dual-Issue OoO

기존 `core_from_home` RTL을 바탕으로 공식 **RVA23S64** 전체 구현을 목표로 개발 중인 RISC-V 코어다. 현재 RTL 시뮬레이션에서 코어·SoC 통합과 Linux 6.12 사용자 모드 벡터 실행을 확인했다. 공식 프로파일 완료 판정에는 전체 규범 조항 검토와 추가 검증이 남아 있다.

## 코어 사양

| 항목 | 현재 구성 |
| --- | --- |
| 합성 및 통합 | `rv23_soc_top`, 기본 XLEN=64, 구현 물리 주소 폭 32비트 |
| 파이프라인 | 2-issue out-of-order, ROB 기반 순차 retire |
| ISA 및 권한 | RV64 정수·단정도/배정도 FP·벡터, M/HS/VS/U/VU, Sv39 및 Sv39x4 |
| 벡터 | VLEN 128비트, ELEN 64비트 |
| L1 | I-cache 32 KiB + D-cache 32 KiB, 캐시별 64비트 2뱅크, 64바이트 라인 |
| SoC | AXI64 시스템 버스, 기본 1 MiB SRAM, CLINT·PLIC, native halt/drain/resume·AXI·retire trace 디버그 |
| RTL 파일 목록 | 저장소 루트 기준 `rtl/filelist.f` 또는 `sim/sources.f` |

뱅크가 다른 접근은 캐시 내부에서 두 64비트 뱅크를 함께 사용할 수 있다. SRAM 리필은 AXI64를 사용한다. [SoC 구성, 주소 맵, 부팅 및 디버그](docs/ARCHITECTURE.md)

전체 시스템 합성 TOP은 [`rv23_soc_top`](rtl/soc/rv23_soc_top.sv)이며,
저장소 루트를 작업 디렉터리로 [rtl/filelist.f](rtl/filelist.f)를 읽는다.
SystemVerilog와 `SYNTHESIS` 정의를 사용한다. 기본 XLEN=64에서 V/H/D/S/MMU가 켜진다.
클록은 `clk_i`이며 별도 SDC/XDC 등의 제약이 필요하다. `CLOCK_HZ` 파라미터는 타이밍 제약이 아니다.
1 MiB SRAM과 캐시의 SRAM/BRAM 매핑을 확인한다. TOP의 `debug_axi_s`는 SV interface이므로
툴이 TOP interface 포트를 지원하지 않으면 일반 신호 포트로 펼친 wrapper가 필요하다.
코어만 합성할 때는 [`rv_ooo_core`](rtl/rv_ooo_core.sv)를 사용한다.

### 파이프라인과 연산기

전체 코어는 큐와 가변 지연 연산기를 가진 OoO 구조여서 단일 고정 N단으로 표시하지 않는다.
정수 ALU 대표 흐름을 아래 **9개 논리 구간**으로 구분했다. frontend의 요청·큐와
backend의 등록 경계를 설명한 것이며, 물리적인 9단 또는 모든 명령의 9사이클 완료를 검증했다는 뜻은 아니다.

```text
① IF/L1 → ② Fetch queue → ③ Decode/UQ → ④ Rename·Dispatch/IQ
→ ⑤ Issue tag/operand → ⑥ Execute/result buffer → ⑦ WB/ROB completion register
→ ⑧ ROB complete 상태 반영 → ⑨ In-order retire
```

| 연산기 | 현재 파이프라인/구조 | 지연과 처리량 |
|---|---|---|
| ADD/SUB·논리·shift, 2개 ALU | ALU 자체는 조합 회로. 코어 경로에 issue tag/operand 등록과 결과 FIFO 등록의 2개 경계 | 연산 뒤 WB·ROB 중재/대기 추가. 실행 결과 preview로 의존 명령을 먼저 깨울 수 있음 |
| 정수 MUL/MULH/MULHSU/MULHU/MULW | 입력 operand 등록 → product/result 등록, 2단 | 모듈 요청 수락→결과 전달 2 cycles, stall 없을 때 매 cycle 새 요청 가능 |
| 정수 DIV/REM, W형 포함 | 단일 iterative divider. 64비트 64회·W형 32회 반복, 별도 DIV tag 등록 1단 | 모듈 일반 연산 65/33 cycles. 0 나누기·signed overflow는 1 cycle. tag 대기와 WB/ROB는 별도 |
| FP FADD/FSUB/FMUL/FMA, F/D·변환 등 | 현재 RVA23 FP: 입력 등록 → 조합 HardFloat/보조 연산 → 결과 등록. 단일 owner 상태 머신 | fast 경로 모듈 지연 2 cycles, backpressure 없을 때 최소 요청 간격 3 cycles. 다단 arithmetic pipeline과 구분 |
| FP FDIV.S / FDIV.D | iterative HardFloat, FP owner 공유 | 가변. `1/3` 실측 28/57 cycles, D의 0 나누기 3 cycles |
| FP FSQRT.S / FSQRT.D | iterative HardFloat, FP owner 공유 | 가변. `sqrt(2)` 실측 26/55 cycles, D의 `sqrt(0)` 3 cycles |
| 벡터 | VLEN128/ELEN64, ROB head의 원소 단위 상태 머신 | VL·SEW·마스크·메모리·예외에 따라 가변. 현재 scalar/vector 경계 직렬화 |

지연의 기준은 **모듈 입력 handshake edge부터 결과 handoff edge까지**, 출력 ready=1,
flush 없음이다. issue→retire 지연은 IQ 대기·결과 중재·선행 명령과 메모리 응답에 따라 달라진다.
FP slow 경로가 owner를 잡은 동안 새 FP 요청도 기다린다.
`CORE_CFG_FPU_LATENCY=6`은 `HAS_D=0` legacy `rv_fpu` 경로의 설정이며,
현재 `HAS_D=1` RVA23의 `rv_fpu_rva23`를 6단 FP로 표시하면 안 된다.
[연산기 지연 실측 근거](docs/evidence/pipeline_latency.json)
· [측정 재현 스크립트](scripts/run_pipeline_latency.py)

### CoreMark 성능

RV64·LP64D, 같은 upstream 알고리즘과 2 KiB performance data의 **10회 RTL 실행 결과**다.
세 빌드 모두 CRC를 통과했다. 실제 합성 clock이나 공식 인증 점수는 아니다.

| 빌드 | Cycles | IPC | CoreMark/MHz 추정 |
|---|---:|---:|---:|
| O2 scalar, 10회 완료 | 4,896,919 | 0.612160 | 2.042100 |
| O3 scalar, 10회 완료 | 4,902,692 | 0.619334 | 2.039696 |
| O3 auto-RVV, 10회 완료 | 11,396,161 | 0.242370 | 0.877488 |

auto-RVV는 실제 벡터 명령을 실행했지만 10회 측정도 O3 scalar보다 약 2.32배 많은 cycles를 썼다. 벡터의 원소 처리·
메모리 경로와 명령 직렬화가 개선 후보이며, IPC만으로 유용 작업량을 비교하지 않는다.
예전에 언급한 IPC 1.123518은 별도의 고정 RV32 ELF 결과다.
[컴파일 옵션·CRC·실측 근거·개선 후보](docs/COREMARK_PERFORMANCE.md)

## 검증 현황

| 검사 | 확인한 결과 |
| --- | --- |
| ACT4 | 체크인 ELF 663/663, 생성 벡터 ELF 2,083/2,083, H·Sv39x4·PMP 보강 ELF 40/40 통과 |
| 후속 ACT4 | upstream이 요구하는 Sail 0.16으로 RVA23 필터의 체크인 ELF 607/607 및 별도 H·Sv39x4·PMP ELF 40/40 통과 |
| 후속 ACT4 생성 벡터 | 2,301/2,301 RTL 실행 통과. Sail 기대값·ELF·로그·현재 RTL 모델의 전체 생성/실행 감사 통과 |
| 스칼라 참조 비교 | 동일 ELF의 Sail/RTL 실행 168개, 사용자 모드 ELF 152개의 retire 기록 61,754건 일치 |
| RV64I HINT 범위 | 31개 연산군의 선택 사례 1,132개, GPR/FPR 스냅샷 72,448개 확인. PAUSE·NTL·FENCE HINT·semihost 표식 포함, Sail/RTL 이벤트 168,849건 일치. [I/M 절별 검토](docs/RVA23_INTEGER_CLAUSE_REVIEW.md) |
| Zicsr RMW | 6개 CSR 명령의 378개 사례와 읽기 전용 예외 114건 확인. 0 쓰기 의도·rd/rs1 중첩·minstret 명시 쓰기 우선순위 검사, Sail/RTL 이벤트 9,182건 일치. [CSR 절별 검토](docs/RVA23_ZICSR_CLAUSE_REVIEW.md) |
| Zimop/Zcmop | M/U 및 압축형의 3,368개 사례에서 목적지 0 쓰기와 C.MOP의 상태 보존을 구분. source/destination 중첩 1,848건, Sail/RTL 이벤트 51,165건 일치. [MOP 절별 검토](docs/RVA23_MOP_CLAUSE_REVIEW.md) |
| Zcb 압축 확장 | RV64 합법 인코딩 1,008개를 포함한 2,300개 사례, Sail/RTL 이벤트 53,712건 일치. 저장 408건 전 바이트 관찰 및 비정렬·경계·중첩 검사. [Zcb 절별 검토](docs/RVA23_ZCB_CLAUSE_REVIEW.md) |
| Zicbop / CMO | PREFETCH.I/R/W의 offset·base 조합 1,413개에서 상태 보존 검사. CBO 권한·ZERO·flush·순서 검증 범위와 함께 [CMO 절별 검토](docs/RVA23_CMO_CLAUSE_REVIEW.md)에 정리 |
| AMO 필드 범위 | W/D 18형식·모든 aq/rl 인코딩·대표 레지스터 중첩과 선택 데이터의 1,728개 사례. 결과와 갱신 메모리를 독립 계산. [A 절별 검토](docs/RVA23_ATOMIC_CLAUSE_REVIEW.md) |
| FP CSR alias | FCSR/FRM/FFLAGS와 여섯 CSR 명령의 1,664개 사례, 이전 값·alias 결과 6,656개 검사 및 Sail/RTL 이벤트 24,109건 일치. [FP 절별 검토](docs/RVA23_FP_CLAUSE_REVIEW.md)에 산술·boxing·상태·권한 근거도 연결 |
| 벡터 FS/VS 권한 | 다섯 모드·host/guest FS/VS의 690개 대표 사례, 허용 234/거부 456건 및 Sail/RTL 이벤트 62,815건 일치. [V 상태 검토](docs/RVA23_VECTOR_CLAUSE_REVIEW.md)에 precise trap·데이터 보존·Dirty 범위 정리 |
| B/Zicond 조항 검토 | Zba 8·Zbb 24·Zbs 8·Zicond 2형식의 구현과 기존 독립 값 검사를 연결. [B/Zicond 검토표](docs/RVA23_BITMANIP_CLAUSE_REVIEW.md)에 word/unsigned-word 및 timing 검증 범위 구분 |
| 남은 규격 검토 | 59개 요구사항을 22개 그룹·47개 열린 검토 주제와 연결. [작업 목록](docs/RVA23_REMAINING_REVIEW.md)은 결함 개수나 전체 검증 완료 판정이 아니며 누락·중복·문서 연결을 필수 감사에서 확인 |
| FENCE.I 코드 동기화 | 148개 자기수정 코드 사례·74개 ignored-field 조합, 같은 ELF의 Sail/RTL 이벤트 2,968건 일치. [검토 결론](docs/RVA23_FENCEI_CLAUSE_REVIEW.md)에 store drain·refill kill·frontend epoch 연결 설명 |
| M 인코딩·소유권 | x0 목적지 65건·예약 형식 예외 36건, 같은 ELF의 Sail/RTL 이벤트 3,910건 일치. XLEN64 component의 active/held flush 20개·재사용 12회 확인. [I/M 검토](docs/RVA23_INTEGER_CLAUSE_REVIEW.md) |
| 기본 동기 예외 | 다섯 모드·네 위임 설정의 100개 사례에서 ECALL/EBREAK/C.EBREAK/illegal16·32, EPC/tval·복귀·instret 비증가를 확인. 같은 ELF의 Sail/RTL 이벤트 8,083건 일치. [검토 결론](docs/RVA23_INTEGER_CLAUSE_REVIEW.md) |
| 지연 store·후속 load | DIV로 store 주소/데이터를 늦춘 448개 사례·896개 값 검사. 같은 ELF의 Sail/RTL 이벤트 21,290건 일치, 실제 LSQ 대기와 더 오래된 SQ/DIV 겹침 관찰. [범위와 한계](docs/RVA23_INTEGER_CLAUSE_REVIEW.md); 전체 RVWMO 검토는 진행 중 |
| 스칼라/벡터 FP 상태 | SEW32/64·다섯 frm·mask/vstart/vl 선택의 교차 실행 160개. 공유 flags와 destination words 640개 확인, Sail/RTL 이벤트 13,507건 일치. [V 상태·실행 검토](docs/RVA23_VECTOR_CLAUSE_REVIEW.md) |
| RV64 압축 명령 | 기존 `rvc` ELF의 Sail/RTL 이벤트 305건 일치. 산술·제어 24형식의 retire 122건과 정수 메모리 8형식을 독립 계산하고 결과·PC·링크·메모리 변조 대조군 33개 거부 |
| RV64 압축 산술 범위 | 18형식의 probe 7,226개, 배치별 동일 ELF의 Sail/RTL 이벤트 62,776건 일치. 즉시값·시프트의 유효 범위와 MV/ADD의 비영 레지스터 쌍 전체, 선택 데이터 패턴 및 대조군 60개 포함 |
| RV64 압축 제어 경계 | 분기·점프 5형식의 probe 3,042개, 배치별 동일 ELF의 Sail/RTL 이벤트 45,146건 일치. 음수 오프셋·2바이트 경계·홀수 간접 포인터·JALR x1 중첩과 대조군 23개 포함 |
| RV64 압축 메모리 범위 | 정수 W/D·FP D 메모리 12형식의 probe 2,448개, 배치별 동일 ELF의 Sail/RTL 이벤트 195,651건 일치. store 1,224건 전 바이트 관찰, 비정렬·라인/물리 페이지 경계·레지스터 중첩 및 대조군 24개 포함 |
| 압축 LR/SC 진행성 | 4/16명령 제한 반복문의 W/D 배치 144개에서 갱신 2,304회 완료. LR 없는 SC 144회를 별도로 실패시켜 압축 재시도 경로도 실행. 동일 ELF의 Sail/RTL 이벤트 29,804건 일치 |
| 압축 HINT·불법 0 | RV64 HINT 394개와 NOP에서 GPR/FPR 스냅샷 값 25,280개·FCSR·SRAM guard 보존 확인. 불법 0의 trap/PC+2 복귀 4회, Sail/RTL 이벤트 59,261건 일치. [C 절별 검토](docs/RVA23_C_CLAUSE_REVIEW.md) |
| FP 비트 동작 | F/D 분류·부호·이동 12형식의 probe 1,110개, 동일 ELF의 Sail/RTL 이벤트 18,532건 일치. 잘못된 S boxing·raw 이동과 `fflags` 보존 포함 |
| FP 비교·min/max | F/D 10형식의 probe 1,215개, 동일 ELF의 Sail/RTL 이벤트 19,099건 일치. NaN·±0 및 NV 누적과 잘못된 결과/flag 대조군 30개 포함 |
| FP·정수 변환 | W/WU/L/LU↔S/D 16형식의 probe 2,760개, 포맷별 동일 ELF의 Sail/RTL 이벤트 합계 36,574건 일치. 5개 정적·동적 반올림 모드와 대조군 48개 포함 |
| FP 포맷 변환 | S↔D·H↔S·H↔D 6형식의 probe 1,600개, 목적지별 동일 ELF의 Sail/RTL 이벤트 합계 23,178건 일치. 직접 D→H 반올림과 대조군 31개 포함 |
| FP 산술·FMA | S/D 18형식의 probe 2,700개, 배치별 동일 ELF의 Sail/RTL 이벤트 합계 54,330건 일치. 5개 정적·동적 반올림 모드, FMA 단일 반올림과 대조군 110개 포함 |
| FP 메모리·half 이동 | 압축 D 메모리 포함 12형식의 probe 688개, 폭별 동일 ELF의 Sail/RTL 이벤트 합계 44,936건 일치. 비정렬/라인/페이지 경계, store 320개 전 바이트 관찰과 대조군 24개 포함 |
| FP 상태·취소 | M 모드 FS/SD·정확한 trap 7건과 분기 취소 8사례 확인. 실제 FP 요청 수락·완료 및 실행 중 FDIV 취소 후 새 FDIV 완료를 관찰했고, 같은 ELF의 Sail/두 RTL 이벤트 409건 일치 |
| FP 권한 매트릭스 | M/HS/VS/U/VU의 host/guest FS 조합 880개, 모드별 동일 ELF의 Sail/RTL 이벤트 합계 80,525건 일치. FS-Off 거부 286건과 host/guest Dirty 갱신 확인 |
| Zfa 추가 FP | RV64 S/D 15형식의 probe 1,447개, 포맷별 동일 ELF의 Sail/RTL 이벤트 합계 32,781건 일치. FLI 상수 32개, 반올림·NaN·모듈러 변환과 대조군 45개 포함 |
| 코어 및 메모리 통합 | dual issue·execute·retire와 독립 명령의 비순차 실행, I/D 뱅크 동시 접근, AXI64 리필, 스칼라·벡터 메모리와 예외·재시작 검사 통과 |
| 기본 1 MiB SRAM | OpenSBI에서 S 모드로 인계, DTB 및 SBI BASE/TIME, 타이머 인터럽트 확인 |
| Linux 6.12 | 32 MiB RTL 시뮬레이션에서 OpenSBI 인계, 사용자 모드 `/init`과 벡터 명령 retire, 정상 종료 확인 |
| Linux 6.14 | 32 MiB RTL 시뮬레이션에서 사용자 포인터 마스킹(Supm) `PMLEN=0→7→0`, 태그 주소의 스칼라·벡터 읽기/쓰기, 정상 종료 확인 |

ACT4 4.1.0의 대규모 회귀는 원래 Sail 핀 0.13.1 대신 H를 지원하는 0.16을 사용했다. 후속 upstream 버전에서는 해당 버전이 요구하는 Sail 0.16으로 H·Sv39x4·PMP 테스트 40개를 모두 통과했다. FPGA 합성·타이밍·실기 적용은 별도 검증이 필요하다. [ACT4 범위와 재현 절차](docs/ACT4_VERIFICATION.md) · [프로파일 조항별 체크리스트](docs/RVA23_IMPLEMENTATION_CHECKLIST.md) · [Linux 콘솔 발췌](docs/evidence/linux-vector-boot-2026-11-17.txt)

## 실행 방법

Windows PowerShell에서 저장소 루트를 기준으로 실행한다. 현재 검증 환경은 `C:/rv_toolchains`의 Verilator 5.050, w64devkit 2.9.1, xPack RISC-V GCC 15.2를 사용했다. 일부 ACT4와 Linux/OpenSBI 스크립트는 `C:/rv_workspaces/rv23` 경로를 사용하므로 다른 경로에 clone했다면 Windows junction을 연결한다.

```powershell
git submodule update --init --recursive
python -m pip install -r requirements-dev.txt
python scripts/check_manifest.py
python scripts/check_rtl.py
python scripts/run_checks.py
python scripts/run_rva23_functional_checks.py --resume
```

검증에 사용한 어셈블리와 테스트벤치는 `sw/tests/`, `tb/`에 있고, 실행·감사 스크립트는 `scripts/`에 있다. 빌드 산출물과 전체 로그는 로컬 `out/`에 생성된다. 이전 RV32 구성은 `python scripts/run_all_rv32_checks.py`로 회귀를 실행할 수 있다.

Linux 6.12 데모는 MSYS2 UCRT64에서 커널 소스를 `out/linux_bringup/linux-6.12`에 풀고 다음 순서로 빌드·실행한다.

```sh
bash scripts/build_linux_image_msys.sh vector
python scripts/run_opensbi_handoff.py --linux-image out/linux_bringup/vector/kbuild-native/arch/riscv/boot/Image --variant vector --linux-vector
python scripts/audit_linux_boot.py --variant vector --require-isa
```

Linux 6.14의 Supm 데모는 아카이브를 `out/linux_bringup/downloads/linux-6.14.tar.xz`에 두고, `out/linux_bringup/linux-6.14/`에 압축을 푼 뒤 실행한다. [Linux 6.14 콘솔 발췌](docs/evidence/linux-supm-boot-2026-11-17.txt)

```sh
bash scripts/build_linux_supm_msys.sh
python scripts/run_opensbi_handoff.py --linux-image out/linux_bringup/supm/kbuild-native/arch/riscv/boot/Image --variant supm --linux-vector --linux-supm
python scripts/audit_linux_boot.py --variant supm --require-isa --require-supm
```

[현재 작업 기록과 검증 결과](docs/REPOSITORY_STATUS.md) · [검증 도구와 실행 범위](docs/VALIDATION.md)

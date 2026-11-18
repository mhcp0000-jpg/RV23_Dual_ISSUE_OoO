# RVA23의 추가 계약 검토

기준은 [RVA23 Profiles 1.0](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html)이다. 아래는 확장 이름이 존재한다는 확인보다 세분한 RTL 연결·동작 검토다. 각 행은 적힌 조건과 실행 근거의 범위만 다룬다. 예를 들어 Sv39의 MODE 지원 확인으로 Sv39 전체를 검증했다고 간주하지 않는다. 전체 ISA·특권 조항 감사와 공식 인증 상태는 별도다.

기존 스칼라 ELF의 근거는 현재 H/V SoC에서 동일 ELF를 재실행한 `out/rva23/profile_hypervisor_replay/report.json`과 함께 사용한다. 현재 기능 회귀는 70단계이며, 아래에 추가한 별도 테스트는 각각 현재 소스·모델·ELF·로그에 묶여 있다.

| 조건 | 확인한 RTL 동작 | 실행 근거와 범위 |
|---|---|---|
| Ziccif: 정렬된 instruction fetch 원자성 | `rv23_cache`의 64비트 bank read와 fill beat 안에 정렬된 16/32비트 parcel이 들어간다. code snoop는 I-cache의 resident/filling 상태와 frontend fence 경로에 반영된다. | `run_instruction_fetch_atomicity.py`: 64B 라인 내 정렬된 32비트 위치 16개와 동일 라인의 code 쓰기/refill 중첩 464회에서 old/new 인코딩과 최종 `FENCE.I`를 확인했다. |
| Za64rs: 예약 집합 크기·정렬 | `rv23_atomic_engine`과 `rv_axi_to_local_bridge`는 주소의 `[31:6]`으로 snoop 범위를 비교한다. monitor는 AXI ID별이며 SC는 주소·폭까지 일치해야 한다. | `run_wrs_debug_wake.py`는 같은 라인의 디버그 쓰기로 WRS.NTO가 깨어나는 네 사례와, 코어 실행 중 LR과 SC 사이에 디버그 AXI 쓰기를 넣는 네 사례를 확인한다. 인접 라인 쓰기 후 SC.W/D가 성공하고, LR 바이트와 겹치는 쓰기 후 SC.W/D가 실패하면서 디버그 값이 보존된다. 새 LR 없이 반복한 SC는 네 경우 모두 실패한다. |
| Ziccrse: 제한된 LR/SC 반복문 진행 | LR/SC는 head owner와 별도 atomic AXI ID를 사용한다. 다른 ID의 읽기는 이 monitor를 소비하지 않는다. cache/버스 요청은 공정한 arbitration과 응답 완료를 거친다. | `run_lrsc_progress.py`: W/D 주소 24개 × IF 위치 3개, 1,152회 성공. 이 실행은 외부 writer/interrupt의 모든 스케줄에 대한 진행성 증명이 아니다. |
| Ziccamoa: main-memory A 연산 | atomic head가 번역·PMP/PMA를 확인하고 SRAM exclusive 경로에서 W/D LR/SC 및 AMO를 실행한다. | 동일 H/V 모델의 atomic/atomic_sv39 ELF, AMO oracle 243개와 fault·reservation 사례, ACT A 테스트. |
| Zicclsm: main-memory 비정렬 접근 | scalar assist는 ROB head 소유권으로 부분 접근을 처리하고, vector 경로는 각 element의 번역·PMA를 확인한다. | 동일 H/V 모델 scalar misaligned ELF, Sv39 경계 fault/retry, vector memory 및 guest partial-fault 테스트. 비정렬 atomic 지원을 주장하지 않는다. |
| Zic64b: block 형상 | cache index/tag와 refill은 6비트 block offset 및 8개 64비트 beat를 사용한다. CBO 경로도 같은 64B 정렬 block을 대상으로 한다. | cache/CBO component와 같은 H/V 모델의 CBO/Sv39 ELF. `rv23_pkg.CACHE_LINE_BYTES=64`. |
| Ssccptr: coherent PTE read | S/VS/G walker의 물리 읽기는 PMP/PMA guard와 공유 PTW/cache 경로를 거친다. D-cache는 accepted SRAM/debug write의 byte strobe를 resident line에 합친다. | `run_ptw_debug_coherence.py`: 정지/실행 중 각각 8회, 64/32비트 쓰기, PTW hit 16회. PTE snoop를 빠뜨린 복사본은 첫 remap에서 거부된다. |
| Sstvecd / Shvstvecd: Direct vector 주소 | CSR commit은 BASE 전체를 보존하고 MODE=0을 허용한다. trap 주소 생성은 Direct이면 BASE를 그대로 사용한다. | `run_profile_csr_geometry.py`: S/VS 각각 canonical 주소 76개의 CSR readback을 확인했다. 별도로 Sv39의 하위 범위 한 곳과 상위 범위 두 곳에 트랩을 전달했다. 페이지 오프셋 `0x004`와 `0xffc`를 사용한 12개 사례에서 handler의 첫 PC와 SRET 복귀를 확인했다. [RVA23 Profiles 1.0](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html) |
| Sscounterenw / Shcounterenw: enable 쓰기 | `HPM_COUNTERS`로 HPM state와 S/H enable mask를 함께 생성한다. production의 구현 HPM3..6 비트는 writable이고 나머지 HPM은 RAZ다. | 960개 counter permission 사례, walking enable와 all-ones readback, HPM event/overflow ELF. |
| Sscofpmf: OF 가시성·LCOFI | `scountovf`는 M에서 활성 OF 전체를, HS에서 `mcounteren`이 허용한 비트를, VS에서 `mcounteren`과 `hcounteren`이 모두 허용한 비트를 제공한다. | `run_hpm_mode_filters.py --overflow-visibility`의 48개 읽기와 HS·VS ECALL 32개를 retire 기록과 대조했다. OF를 CSR로 설정해도 LCOFIP는 0을 유지했고 구현하지 않은 카운터 31은 0이었다. 별도 실행은 다섯 모드의 필터와 실제 wrap 이후 OF 재설정·LCOFI를 확인한다. [Sscofpmf 1.0](https://docs.riscv.org/reference/isa/v20260120/priv/sscofpmf.html) |
| Ssu64xl: UXL=64 | physical/virtual S status read 경로가 UXL=2를 제공한다. | S/VS status 각각 UXL 쓰기 0..3 후 readback. 구현은 UXL=64를 유지한다. |
| Svbare / Shvsatpa / Shgatpa: MODE 대응 | `satp`·`vsatp`는 Bare/Sv39를 지원하고 미지원 MODE가 들어오면 전체 쓰기를 무시한다. `hgatp`는 Bare/Sv39x4를 지원한다. 미지원 MODE 쓰기는 MODE를 유지하면서 16 KiB로 정렬된 새 루트 PPN을 반영한다. | 미지원 MODE 14개를 Bare와 Sv39x4에서 각각 쓴 28개 사례를 포함해 전체 CSR 검사 279개가 통과했다. 같은 ELF는 수정 전 218번 사례에서 실패하고 수정 후 전체 SoC에서 통과했다. [H 확장 규격](https://docs.riscv.org/reference/isa/v20240411/priv/hypervisor.html) |
| Svade: A/D 처리 | read-only walker는 A=0 또는 store의 D=0을 permission fault로 처리하며 PTE를 쓰지 않는다. VS PTE의 G-stage 번역은 load 권한으로 검사하고 예외는 원래 명령의 접근 종류로 보고한다. | MMU 테스트 103개에는 VS 및 최종 G leaf의 A/D 조합과 암시적 PTE read의 A=0이 포함된다. 원래 fetch/load/store별 cause와 최종 접근 GPA 및 PTE GPA를 대조했다. Native S-mode `rv64si/dirty` Sail 비교는 소프트웨어의 A/D 수정 및 재시도를 확인한다. [특권 규격](https://docs.riscv.org/reference/isa/priv/hypervisor) |
| H: 암시적 VS PTE 읽기의 MXR | G-stage leaf가 실행 전용이면 HS MXR이 암시적 읽기 허용 여부를 결정한다. VS MXR은 G-stage 권한에 영향을 주지 않는다. | `run_guest_pte_mxr.py`는 각 사례에서 변환 캐시를 비운 뒤 동일 ELF에서 HLV.D·HLVX.WU·HSV.D 36개를 실행한다. Sail과 RTL의 2,302개 이벤트가 일치했다. G-stage의 A=0과 MXR으로 허용되지 않은 실행 전용 매핑의 예외 18건에서 `htval`과 `htinst`를 확인했다. [H 규격](https://docs.riscv.org/reference/isa/priv/hypervisor) |
| H: 명시적 게스트 접근의 SPVP·SUM | `hstatus.SPVP`가 VS/VU 유효 권한을 선택한다. VS가 U 페이지를 접근할 때는 `vsstatus.SUM`을 사용한다. | `run_guest_access_sum.py`는 M·HS의 HLV.D·HLVX.WU·HSV.D 96건에서 PTE.U, SPVP, HS/VS SUM을 조합했다. PTE가 같은 동안 HFENCE 없이 권한 설정을 바꿨고 정상 접근 60건과 페이지 예외 36건의 결과·EPC·tval·GVA 및 메모리 보존을 확인했다. 동일 ELF의 Sail·RTL 이벤트 5,801개가 일치했다. [H 1.0 게스트 메모리 접근](https://docs.riscv.org/reference/isa/priv/hypervisor.html) |
| Ssstateen: S/H CSR view | `rv_hypervisor_stateen`이 S/H 각각 4개 view를 decode한다. H의 SE/ENVCFG와 S의 optional-state RAZ를 제공하고 CSR file의 trap 경로에 연결된다. | CSR geometry의 8개 view read/write와 별도로 `run_guest_stateen.py`가 게이트 7개 조합에서 VS 읽기 42건을 실행했다. 각 `hstateen[n].SE`는 해당 `sstateen[n]`을, `hstateen0.ENVCFG`는 `senvcfg`를 제어했다. 차단된 32건의 cause 22, 명령 인코딩과 `stval`, SRET 복귀를 확인했다. [Ssstateen 규격](https://docs.riscv.org/reference/isa/priv/smstateen.html) |
| Sstvala / Shvstvala: VA·명령 trap 값 | fetch queue가 16비트 parcel을 zero-extend한다. decode가 압축 명령을 확장해 해석하더라도 illegal-instruction trap에는 원본을 전달한다. S/VS CSR bank가 위임된 trap의 값을 기록한다. | breakpoint·illegal matrix의 88개 사례에서 각 trap handler가 EPC와 tval을 읽고 복귀했다. 그중 55개는 예약된 `C.ADDI4SPN` 또는 FS=Off의 네 압축 D 명령이다. 게스트 사례는 호스트 FS를 켜 둔 상태에서 VS의 FS 검사도 확인했다. 주소 근거는 scalar/vector memory fault와 split-fetch 12개 사례, virtual-instruction 근거는 privilege matrix를 참조한다. [RVA23 Profiles 1.0](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html) |
| Shtvala: faulting guest PA | H CSR bank는 guest-page fault에 전달된 guest address를 2비트 우측 이동해 htval에 기록한다. implicit VS-PTE read는 별도 metadata를 전달한다. | G-stage/guest-memory ELF, MPRV implicit/explicit 10개 사례. split-fetch의 두 G-stage 사례는 뒤쪽 parcel GPA와 shifted htval/mtval2를 확인한다. |
| Supm / Ssnpm: PMLEN=0/7 | S/H envcfg와 HUPMM은 PMM=00/10을 지원하고 unsupported 값은 이전 legal PMM을 유지한다. pointer-mask 결과가 scalar/FP/A/CBO/V 주소 경로에 연결된다. | `run_supm_user.py`에서 U 모드가 `ECALL`로 HS 실행 환경에 `PMLEN=0→7→0`을 요청했다. Bare와 Sv39의 여섯 요청에서 `senvcfg`를 확인했다. 태그 주소의 정상 load/store 4건과 마스킹을 끈 상태의 예외 8건을 대조했다. bare-metal HS 서비스의 동일 ELF로 Sail과 RTL의 PC·명령·예외 cause·레지스터 결과 798개 이벤트를 대조했다. [RVA23 Profiles 1.0](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html) |
| RV64I 프로파일 기본 조건 | U `ECALL`은 `medeleg` 설정에 따라 S에 전달된다. S `ECALL`은 M 실행 환경에 요청을 전달한다. | 같은 Supm ELF가 U→HS의 cause 8, HS→M의 cause 9와 저장된 EPC·tval을 확인했다. `SD`로 쓴 값의 첫 바이트를 `LBU`로 읽어 Bare와 Sv39에서 little-endian 바이트 순서를 확인했다. [RVA23 Profiles 1.0](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html) |
| Zkt / Zvkt: 데이터 독립 지연 | scalar 고정 pipeline과 vector element/state 진행 조건을 검토했다. arithmetic data가 완료 시점을 바꾸지 않는 경로와 mask/control 예외를 구분한다. | scalar 동일-text 16개와 vector 84,348 paired probe, operand-dependent early-exit 복사본 거부. 범위는 `TIMING_CONTRACT.md`에 명시한다. |
| Svpbmt / Svnapot: PTE 속성 | walker는 PBMT reserved/disabled 값을 거부하고 64KiB NAPOT leaf의 인코딩과 주소 합성을 검사한다. | MMU 테스트는 VS/G PBMT 3×3 조합과 양쪽 PBMTE, S 및 VS/G의 64 KiB 서브페이지를 확인한다. 비정렬 HLV.D 9개는 최종 유형을 실제 접근에 적용하며 수정 전 모델은 같은 ELF에서 실패한다. |
| Sv39 / Sv39x4: 중간 PTE 인코딩 | 페이지 워커는 non-leaf PTE의 A·D·U, N·PBMT와 상위 예약 비트를 검사한다. | `run_pte_nonleaf_contract.py`는 S·VS와 G-stage의 최종 접근·암시적 VS PTE 읽기에서 load/store 144건을 실행했다. G·RSW를 포함한 정상 접근 32건, 예약 비트의 페이지 예외 112건을 확인했다. 암시적 G-stage 실패는 VS 루트 PTE의 GPA를 `htval`에 기록했고 `htinst=0x3000`이었다. 동일 ELF의 Sail·RTL 이벤트 9,997개가 일치했다. [Sv39 규격](https://docs.riscv.org/reference/isa/priv/supervisor.html) · [H 1.0](https://docs.riscv.org/reference/isa/priv/hypervisor) |

## 추가한 경계 사례

### Zcb의 전 합법 인코딩 및 좁은 메모리 접근

`scripts/run_zcb_contract.py`는 RV64의 12개 Zcb 형식에 대해 고유 합법 인코딩
1,008개를 포함한 2,300개 사례를 전체 H/V RTL에서 실행한다. 배치별 동일 ELF의
Sail/RTL 이벤트 53,712건이 일치했다. 독립 정수/바이트 모델로 store 408건 전
바이트와 base/data 중첩 172건, 비정렬 24건, 라인 경계 12건, Bare 물리 페이지
경계 6건 및 FCSR 보존을 검사하며 변조 대조군 20개를 거부한다.

원본 16비트 instruction과 PC+2는 그대로 비교한다. byte oracle에 전달하는
별도 복사본에서만 target memory 명령을 동등한 일반 load/store로 변환한다.
현재 활성 의존 확장의 M-mode 실행이며, 모든 입력 값이나 fault/privilege/스케줄을
포괄하지 않는다. [Zcb 절별 검토](RVA23_ZCB_CLAUSE_REVIEW.md)에 범위를 연결한다.
`--check`를 필수 통합 감사에 추가했다.

### Zimop의 0 쓰기와 Zcmop의 no-write 기본 의미

기준은 [Zimop/Zcmop 1.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zimop.html)이다.
`scripts/run_mop_contract.py`는 의미를 재정의하는 확장이 없는 현재 기본 동작을
같은 전체 H/V SoC와 Sail에 배치별 같은 ELF로 실행한다. 인코딩의 number
필드는 [공식 riscv-opcodes의 Zimop 정의](https://github.com/riscv/riscv-opcodes/blob/master/extensions/rv_zimop)와 대조했다.

| 대상 | 실제 검사 |
|---|---|
| MOP.R.0~31 | 모든 rd=x0~x31에 별도 source와 rd=rs1을 조합 |
| MOP.RR.0~7 | 모든 rd에 별도 source, rd=rs1, rd=rs2 및 rd=rs1=rs2를 조합 |
| M/U | M mode 3,072개와 전 40형식의 U mode 선택 사례 288개. U 종료 ECALL 외에 trap을 허용하지 않음 |
| R/RR 결과 | 목적지의 초기값을 비영 값으로 채워 현재 기본 동작이 단순 NOP가 아니라 0 쓰기임을 확인. 바뀌지 않아야 할 source 값과 FCSR도 자체 검사 |
| C.MOP.1/3/5/7/9/11/13/15 | 8개 모두 no-write. 기존 immutable snapshot scaffold에서 GPR/FPR 512개 값과 FCSR/guard 보존, PC+2 확인 |

총 3,368개 probe에서 source/destination 중첩 1,848건과 무시된 목적지 x0
192건을 확인했다. 같은 ELF의 Sail/RTL 이벤트 51,165건이 일치했고, 결과나
FCSR 및 compressed snapshot/예외 값을 바꾼 trace 대조군 92개를 거부했다.
이는 변경 RTL 실행이 아니다. 현재 reference 설정에서 Zicfilp/Zicfiss는 비활성이다.

`out/rva23/mop_contract/report.json`과 `--check`가 현재 RTL/model·Sail·ELF·
assembly·trace·로그·공유 snapshot helper의 해시 및 기대값을 재검사한다.
모든 source register 직교 조합이나 H/VS/VU 상태, 재정의된 MOP 기능 또는
RVWMO dependency의 보편적 증명을 뜻하지 않는다. [절별 검토표](RVA23_MOP_CLAUSE_REVIEW.md)에 연결한다.

### Zicsr의 encoded-zero와 명시적 counter 쓰기

기준은 [Zicsr 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zicsr.html)이다.
`scripts/run_zicsr_rmw_contract.py`는 6개 CSR 명령을 mscratch·minstret·mhartid에
적용한 378개 사례를 같은 전체 H/V SoC와 Sail에서 같은 ELF로 실행한다.
읽기 전용 CSR에 대해 RS/RC가 쓰기를 시도하는지는 operand 값 0이 아니라
인코딩의 rs1=x0 여부로 결정된다. immediate RS/RC는 uimm=0이면 쓰지 않는다.

| 조건 | 실제 검사 |
|---|---|
| 6개 RMW 형식 | register형 rd=x0/x5/x31, rs1=x0/x5/x31와 선택 64비트 값. immediate형은 uimm=0/1/15/16/31 |
| encoded rs1≠x0, 값 0 | RS/RC 36건. writable CSR 및 read-only 쓰기 의도를 구분 |
| rd=rs1 | 72건. 기존 source를 CSR에 적용하면서 기존 CSR 값을 rd에 반환 |
| 읽기 전용 접근 | mhartid 쓰기 의도 114건은 cause 2·정확한 PC·원본 instruction tval·writeback 없음. 억제된 RS/RC 쓰기는 trap 없이 읽음 |
| 자기 갱신 counter | 실제 retire마다 독립 64비트 minstret 모델을 갱신한다. 명시적 CSR 쓰기는 해당 명령의 자동 증가를 덮어쓰며 trap은 retire 증가에 포함하지 않음 |
| 인접 counter 읽기 | 실제 ELF에서 write/read/read가 연속한 32비트 명령임을 확인. 0x1234를 쓰고 다음 두 읽기에서 0x1234, 0x1235를 확인 |

총 minstret 읽기 212건·명시적 쓰기 242건의 값과 같은 ELF의 Sail/RTL 이벤트
9,182건이 일치했다. 기존 counter permission matrix의 `write_zero`는 주로
CSRRW x0를 사용하므로 이번 encoded-zero 및 RMW 조합과 구분한다.
CSR 이전 값·readback·counter read·trap cause/tval을 바꾼 trace 대조군 5개를
독립 검사기가 거부했다. 이는 변경 RTL 실행이 아니다.

`out/rva23/zicsr_rmw_contract/report.json`과 `--check`는 현재 RTL/model,
Sail·ELF·assembly·trace·로그·독립 검사 helper를 해시로 연결한다.
이 M-mode 검사는 세 CSR의 명령 의미를 다룬다. 전체 CSR bank의 WARL,
다른 권한 모드, custom read/field-write side effect나 외부 agent 순서의
검증은 아니다. 표준 CSR에 read side effect가 없으므로 CSRRW rd=x0의
내부 read strobe 억제를 직접 관찰했다고 하지 않는다.
[Zicsr 절별 검토표](RVA23_ZICSR_CLAUSE_REVIEW.md)에 공유 범위를 연결한다.

### RV64I HINT의 형식별 상태 보존

기준은 [RV64I 2.1 HINT 표](https://docs.riscv.org/reference/isa/v20260120/unpriv/rv64.html)와
[상속하는 RV32I 2.1의 FENCE/HINT](https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html)다.
`scripts/run_rv64i_hint_contract.py`는 31개 기본 연산군과 특수 표식의 선택 사례
1,132개를 같은 전체 H/V SoC와 Sail에서 배치별 같은 ELF로 실행한다.
RV64I의 큰 HINT 공간 전체를 열거한 결과로 간주하지 않는다.

| 분류 | 선택한 실행 범위 |
|---|---|
| LUI/AUIPC rd=x0 | U immediate의 20개 bit 위치와 0·부호·최댓값 경계 |
| I/ADDIW rd=x0 | rs1=x0/x1/x8/x15/x31, immediate=-2048/-1/0/1/2047. SLTI/SLTIU custom HINT도 현재 inert 정책으로 검사 |
| R/RW rd=x0 | 각 연산의 rs1/rs2 필드가 모든 레지스터를 포함하도록 선택한 쌍과 zero/self 쌍. ADD의 NTL 네 코드 포인트 포함 |
| Shift-immediate rd=x0 | RV64 shift 0~63 및 W shift 0~31 각각에 선택 rs1. standalone semihost entry/exit 표식 추가 |
| Null-set FENCE | fm=0이고 pred 또는 succ가 0인 31개 mask 조합과 (rd,rs1)=(0,0)/(0,31)/(31,0). PAUSE 포함 |

기존 압축 HINT의 snapshot scaffold는 수정하지 않고 재사용한다. 새 생성기는
라벨이 붙은 probe directive만 32비트로 바꾸고, 실제 trace에서는 원래 인코딩과
PC+4, 64개 snapshot store 및 load의 인코딩·값을 별도로 검사한다.
GPR/FPR snapshot 72,448개, FCSR과 인접 SRAM guard의 보존을 확인했고,
Sail/RTL 이벤트 168,849건이 일치했다. 분류별 snapshot 값을 바꾼 trace 대조군
44개를 독립 검사기가 거부했다. 이는 변경 RTL 실행이 아니다.

`out/rva23/rv64i_hint_contract/report.json` 및 `--check`가 현재 RTL/model,
Sail·ELF·assembly·trace·로그와 immutable scaffold의 해시를 연결한다.
이 검사는 M mode·FS Dirty의 선택 상태에 관한 것이다. semihost 서비스 ABI,
모든 CSR/권한, HINT 지연과 전역 순서를 검증하지 않는다. 실제 버스 ordering은
별도 `run_fence_order.py`의 backpressure/응답/retire 계측과 함께 검토한다.
[I/M 절별 검토표](RVA23_INTEGER_CLAUSE_REVIEW.md)는 공유 조항과 남은 범위를 연결한다.

### RV64C HINT의 상태 보존과 영 인코딩 예외

기준은 [C 2.0의 HINT 표와 불법 영 인코딩](https://docs.riscv.org/reference/isa/v20260120/unpriv/c-st-ext.html)이다.
`scripts/run_rvc_hint_contract.py`는 RV64의 HINT 코드 포인트 394개와 기본 NOP를
빠짐없이 생성해 전체 H/V SoC와 Sail에 배치별 같은 ELF로 실행한다.
기존 65,536개 expander 검사는 확장 설정 간 변화 검사이며, 기본 C의 모든
인코딩을 독립 ISA oracle로 판정한 근거로 확대 해석하지 않는다.

| 분류 | 실행 코드 포인트 |
|---|---:|
| NOP / NOP HINT | 1 / 63 |
| ADDI imm=0 / LI rd=x0 / LUI rd=x0,nzimm | 31 / 64 / 63 |
| MV rd=x0 / ADD rd=x0 | 31 / 31 (NTL 네 형식 포함) |
| SLLI rd=x0 또는 shamt=0 | 중복 제외 95 |
| SRLI/SRAI shamt=0 | 각 8 |

HINT 직전 모든 GPR/FPR의 기준값을 확인하고, 직후 GPR 32개와 FPR 32개를
SRAM으로 snapshot한 뒤 64개 값을 다시 읽는다. 레지스터 snapshot 값 총
25,280개와 FCSR=0x65, 인접 SRAM guard 790회 읽기가 기준과 일치했다.
rd=x0에 대한 무시된 writeback과 같은 값을 쓰는 self-write는 허용한다.
custom용 shift HINT 공간은 현재 구현의 inert 동작으로 검사한다.

각 ELF 끝에서는 영 16비트 명령을 실행한다. PC mod 4=0/2의 네 trap에서
cause 2, 원래 instruction tval=0, writeback 없음, 원래 EPC 및 PC+2 복귀를
확인했다. Sail/RTL 이벤트 59,261건이 일치했다. GPR/FPR snapshot·FCSR·trap
cause/tval을 바꾼 trace 대조군 20개를 독립 검사기가 거부했다. 변경 RTL 실행은 아니다.
보고서는 `out/rva23/rvc_hint_contract/report.json`이며 `--check`가 현재 RTL/model,
Sail·ELF·assembly·trace·로그·byte oracle helper를 해시로 묶어 재검사한다.

이 검사는 M mode·FS Dirty의 데이터/FCSR/guard 상태를 다룬다. 모든 CSR 및
권한 조합이나 HINT의 미세구조 효과를 측정한 것은 아니다. reserved 공간은
영 인코딩과 구분하며, Zcb/Zcmop가 합법화하는 인코딩을 일괄 illegal로 취급하지 않는다.
전체 C 조항과 공유 경로의 범위는 [절별 검토표](RVA23_C_CLAUSE_REVIEW.md)에 연결한다.

### C 명령을 포함한 제한된 LR/SC 반복문

기준은 [C 2.0의 LR/SC 사용 조항](https://docs.riscv.org/reference/isa/v20260120/unpriv/c-st-ext.html)과
[A 2.1의 eventual success](https://docs.riscv.org/reference/isa/unpriv/a-st-ext.html)다.
기존 `run_lrsc_progress.py`는 `.option norvc`의 LR/ADDI/SC/BNEZ만 실행했으므로
압축 명령을 포함하는 조항의 직접 실행 근거와 구분한다.

`scripts/run_compressed_lrsc_contract.py`는 W/D 데이터의 64B 내 모든 정렬
위치와 명령 라인 offset 0/32/62, 두 반복문 크기를 조합한 144개 배치를 실행한다.
각 배치는 성공 16회 뒤 최종 값을 다시 load한다. 전체 H/V SoC와 Sail은 같은 ELF를 쓴다.

| 구조 | 실제 ELF에서 확인한 제한 |
|---|---|
| 최소 반복문 | LR.aq, C.ADDI, SC.rl, C.BNEZ: 4명령·12바이트 |
| 최대 명령 수 반복문 | LR.aq와 SC.rl 사이의 C.MV/ADDI/XOR/OR/AND/SUB/ADD/ANDI 13명령 및 C.BNEZ: 16명령·36바이트 |
| 재시도 경로 | C.BNEZ a1의 nonzero 경로가 LR로 돌아가는지 ELF 필드 및 실제 trace에서 확인 |
| 라인 경계 | LR의 line offset 62 및 최대 반복문에서 SC의 line offset 62를 포함. 32비트 원자 명령이 64B IF 라인을 가로지름 |
| 사전 실패 검사 | 각 배치는 처음에 LR 없이 SC 위치로 진입한다. 반드시 실패하고 압축 backedge를 거친 뒤 정상 LR/SC 실행. 이 첫 시도는 제한된 LR/SC 진행성 성공에 포함하지 않음 |

독립 검사기는 ELF의 실제 명령 개수·바이트 수·retry 목적지, LR의 메모리 값,
압축 산술 결과와 분기 목적지, SC 주소/폭/입력 및 성공 시의 바이트 갱신과 최종
load를 검사한다. 총 LR 2,304회·SC 2,448회, 성공 갱신 2,304회 및 의도한 사전
실패 144회가 관찰됐다. 이 실행에서 추가 spurious SC 실패는 없었고, 같은 ELF의
Sail/RTL 이벤트 29,804건이 일치했다. ISA는 spurious 실패를 허용하며 exact
trace 비교는 현재 실행의 더 강한 회귀 근거이지 모든 합법 구현에 대한 제약은 아니다.

LR/SC/압축 결과·최종 load·retry PC·retry layout을 바꾼 대조군 6개를 독립
검사기가 거부했다. 이는 trace/ELF byte 모델 변조이며 변경 RTL 실행은 아니다.
`out/rva23/compressed_lrsc_contract/report.json`과 `--check`가 현재 RTL/model,
같은 ELF·Sail·assembly·trace·로그·helper의 해시를 확인한다. 이 유한 진행성
검사는 보편적 liveness, 다른 master의 지속적인 간섭이나 공정성을 증명하지 않는다.

### RV64C 메모리의 오프셋 필드와 바이트 관찰

기준은 [C 2.0의 load/store](https://docs.riscv.org/reference/isa/v20260120/unpriv/c-st-ext.html)다.
`scripts/run_rv64c_memory_contract.py`는 정수 LW/LD/SW/SD와 FP FLD/FSD의
일반 압축형 및 SP형, 총 12형식의 probe 2,448개를 13개 ELF로 실행한다.
각 배치에서 Sail과 전체 H/V SoC는 같은 ELF를 사용한다.

| 조건 | 실행 검사 |
|---|---|
| 일반 압축형 | 형식별 offset 32개 각각에 base x8~x15를 사용하며 data 레지스터를 바꾼다. base/data의 8×8 조합이 모두 존재 |
| SP형 | 형식별 offset 64개를 선택 data 레지스터 두 개와 결합. 정수 load는 x1~x31, 정수 store는 x0~x31, FP는 f0~f31 모두 포함 |
| 데이터 | 0·전부 1·word 부호 경계·상위 32비트가 있는 값, FP signed zero와 qNaN/sNaN의 raw payload를 포함 |
| 정수 base/data 중첩 | load 목적지 또는 store 소스와 base가 같은 242건. load는 기존 base로 주소를 계산하고, alias store는 실제 base 값을 저장해야 함 |
| 비정렬·경계 | 비정렬 136건, 64B 라인 경계 64건과 Bare 물리 4KiB 경계 24건. 가상 페이지 변환 fault를 뜻하지 않음 |
| 상태 보존 | FPR load 목적지를 기대값의 보수로 초기화하며, 정수 alias load는 기존 base 유지. load/store 뒤 fflags 0/5/31 누적값 보존 확인 |

독립 모델은 ELF의 file-backed 바이트와 실제 프로그램의 정수 store로 초기
메모리를 구성한다. 각 대상 store의 모든 바이트가 후속 guard load에서
관찰돼야 하며, 주변 32바이트의 내용도 검사한다. 미초기화 SRAM을 0으로
가정하지 않는다. store 1,224건 전부의 전 바이트를 관찰했고, 동일 ELF의
Sail/RTL 이벤트 195,651건이 일치했다. load 결과 또는 후속 guard read 값을
바꾼 trace 대조군 24개를 거부했다. 이는 변경 RTL 실행이 아니다.

보고서는 `out/rva23/rv64c_memory_contract/report.json`이며 `--check`가
생성 assembly와 현재 RTL/model·Sail·ELF·trace·로그·byte oracle helper의
해시를 확인하고 검사를 반복한다. 이 유한 필드 검사는 전체 피연산자의 직교
조합, 변환 fault/권한, 외부 master와의 경합·MMIO 원자성 및 모든 스케줄을
대신하지 않는다.

### RV64C 분기·점프의 부호 경계와 소스/링크 중첩

기준은 [C 2.0의 제어 이전](https://docs.riscv.org/reference/isa/v20260120/unpriv/c-st-ext.html)이다.
`scripts/run_rv64c_control_contract.py`는 5형식의 probe 3,042개를 16개 ELF로
나눠 같은 전체 H/V SoC와 Sail에 사용한다. 원래 16비트 필드와 실행 전
레지스터를 읽고 실제 다음 PC 및 링크를 독립 계산한다.

| 형식 | 실행 조건 |
|---|---|
| C.J | -2048/2046 양 끝과 부호·비트 위치·짧은 거리를 포함한 25개 offset, 명령 PC mod 4=0/2 |
| C.BEQZ/BNEZ | -256/254 양 끝 등을 포함한 20개 offset, rs1′=x8~x15, 0·1·전부 1·bit 63만 켠 입력. offset=0은 not-taken만 실행 |
| C.JR/JALR | rs1=x1~x31 각각에 주소 bit 0=0/1, 명령 및 목적지의 PC mod 4=0/2 조합 |
| C.JALR x1 | 기존 x1의 목적지로 이전한 뒤 x1에 PC+2 저장. 위 정렬·홀수 포인터 조합 8개 |

목적지에는 2바이트 반환 trampoline을 두어 offset=-2도 겹치는 인코딩 없이
실행하고, 분기 미실행 경로는 PC+2에서 별도 trampoline을 실행한다. 각 probe는
한 번만 retire해야 하며 trap을 허용하지 않는다. C.JR/JALR의 홀수 입력
248건은 bit 0이 제거된 주소로 이전했다. 다음 PC가 4바이트 경계에서 2바이트
떨어진 사례 1,521건을 포함해 Sail/RTL 이벤트 45,146건이 일치했다.

각 배치의 형식별 다음 PC와 JALR 링크를 바꾼 trace 대조군 23개를 거부했다.
이는 변경 RTL 실행이 아니다. `out/rva23/rv64c_control_contract/report.json`과
`--check`가 생성 assembly·현재 RTL/model·Sail·ELF·trace·로그·helper를
해시로 묶고 동일 검사를 다시 수행한다. 이 경계 검사는 모든 오프셋이나
taken zero-offset 무한 루프의 인터럽트 탈출, 변환 fault 및 전체 스케줄을
검증했다고 간주하지 않는다.

### RV64C 산술의 즉시값·시프트·레지스터 필드 범위

기준은 [C 2.0의 정수 계산 명령](https://docs.riscv.org/reference/isa/v20260120/unpriv/c-st-ext.html)이다.
`scripts/run_rv64c_compute_contract.py`는 다음 18형식의 새 probe 7,226개를
13개 ELF로 나눠 전체 H/V SoC와 Sail에서 실행한다. 각 배치는 같은 ELF를
사용한다. 명령의 수치 의미와 16비트 필드 해석을 별도로 계산해 operand 초기값,
목적지 writeback 및 다음 PC+2를 모두 검사한다.

| 형식 | 실행한 필드 범위와 데이터 |
|---|---|
| ADDI/ADDIW/ANDI | 즉시값 -32~31 각각에 선택 64비트 입력 8개. ADDI의 imm=0 HINT 포함 |
| LI/LUI | rd=x1/x8/x31, LI의 -32~31 및 LUI의 0을 제외한 63개 즉시값. 목적지를 기대값의 비트 보수로 초기화 |
| SLLI/SRLI/SRAI | shift 0~63 각각에 선택 입력 8개와 변하는 rd. shift=0 HINT 포함 |
| ADDI16SP | -512~496의 16배수 중 0 제외 63개에 입력 3개 |
| ADDI4SPN | 4~1020의 4배수 255개에 입력 2개, rd′를 변경 |
| SUB/XOR/OR/AND/SUBW/ADDW | rd′/rs2′의 8×8 쌍 각각에 선택 입력 패턴 3개 |
| MV/ADD | rd/rs2의 비영 31×31 쌍 전체. 목적지와 입력의 alias 포함 |

입력 패턴은 0, 전부 1, 1, 64비트 최상위 비트, 32비트 부호 경계와 상위
32비트가 0이 아닌 값을 포함한다. word 연산은 low 32-bit 결과를 부호 확장한다.
전체 7,226개 probe에서 Sail/RTL 이벤트 62,776건이 일치했다. 형식별 결과나
다음 PC를 바꾼 trace 대조군을 배치별로 적용해 총 60개를 거부했다.

보고서는 `out/rva23/rv64c_compute_contract/report.json`이다. `--check`는
생성된 assembly와 현재 RTL/model·ELF·Sail·trace·로그·helper의 해시를 확인하고
독립 검사를 다시 수행한다. 이 필드 범위 검사는 모든 피연산자의 직교 조합,
다른 압축 명령의 메모리·제어 이전·예외, 권한 또는 전체 스케줄을 대신하지 않는다.

### RV64C의 직접 인코딩 계산과 다음 PC

기준은 [C 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/c-st-ext.html)이다.
`scripts/audit_rv64c_contract.py`는 기존 전체 H/V SoC의 `rv64uc/rvc` 실행을
다시 읽는다. 같은 ELF를 사용한 Sail/RTL 이벤트 305건을 재대조하고, DUT의
expander 출력 대신 원래 16비트 필드와 직전 정수 레지스터 값으로 의미를 계산한다.

산술·제어 24형식(NOP 포함)의 retire 122건에서 즉시값과 word 부호 확장,
순차 PC+2 및 분기·jump 목적지를 확인했다. BEQZ/BNEZ는 taken/not-taken
양쪽이 있고 JALR은 링크가 PC+2인지 별도로 검사한다. 같은 ELF 바이트 모델로
LW/LD/SW/SD 및 각 SP 형식 8종의 메모리 명령 13건을 검사하며, 네 store
모두 후속 load에서 관찰된다. 관찰되지 않은 메모리를 0으로 가정하지 않는다.

형식별 결과/다음 PC 대조군 24개, JALR 링크를 PC+4로 바꾼 대조군 1개,
압축 load 결과 4개 및 store offset 4개를 바꾼 대조군을 모두 거부했다.
이는 trace 변조 검사이며 다른 RTL을 실행한 결과는 아니다. 현재 RTL/model,
Sail, upstream 입력 및 ELF·trace·로그·독립 검사 helper를 해시로 연결한
보고서는 `out/rva23/rv64c_contract_audit.json`이다.

이 감사는 기존 실행에 독립 의미 검사를 추가한다. C.EBREAK 예외, FP 압축
메모리, 예약/HINT 인코딩과 전 즉시값·피연산자·스케줄 조합을 이 결과로
검증했다고 간주하지 않는다.

### Zfa의 상수·반올림·조용한 비교와 모듈러 변환

기준은 [Zfa 1.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zfa.html)이다.
`scripts/run_zfa_contract.py`는 RV64 S/D에서 필요한 15형식을 전체 H/V
SoC와 Sail에 포맷별 같은 ELF로 실행한다. Python의 비트·유리수 모델로
독립 기대값을 계산하고 실제 operand, 목적지 writeback과 `fflags`를 검사한다.
각 목적지는 기대값의 비트 보수로 미리 채워 결과 갱신도 관찰한다.

| 형식 | 실행 검사 |
|---|---|
| FLI.S/D | 인덱스 0~31 전부, 포맷별 최소 양의 정규수, infinity·canonical NaN, flags 보존 |
| FMINM/FMAXM.S/D | 어느 입력이든 NaN이면 canonical NaN, sNaN의 NV, ±0의 선택과 잘못된 S boxing |
| FROUND/FROUNDNX.S/D | 정적·동적 5개 반올림 모드, signed zero·무한대·NaN, NX를 올리는 형식과 올리지 않는 형식 구분 |
| FLTQ/FLEQ.S/D | qNaN에서는 false이며 NV 없음, sNaN에서는 NV, signed zero와 boxing |
| FCVTMOD.W.D | RTZ로 자른 무한 정밀 정수의 low 32-bit를 sign extend. NaN/무한대 결과 0, flags는 일반 FCVT.W.D RTZ와 동일하게 검사 |

S 724개·D 723개, 총 1,447개 probe와 같은 ELF의 Sail/RTL 이벤트
32,781건이 일치했다. 초기 flags를 누적하며 반올림을 사용하지 않는 형식은
예약된 `frm` 값의 영향도 받지 않는지 확인했다. 각 형식의 결과 또는 NX/NV를
바꾼 trace 대조군 총 45개를 검사기가 거부했다. 이는 변조한 RTL 실행은 아니다.
보고서는 `out/rva23/zfa_contract/report.json`이며 `--check`가 현재 RTL/model,
ELF·trace·로그·생성기·참조 모델 해시를 확인하고 독립 검사를 다시 수행한다.

이 유한 검사는 profile의 Zfhmin/Zvfhmin보다 넓은 full half 연산이나 Q,
RV32 전용 transfer 형식을 요구하지 않는다. 예약 rm의 trap과 모든 FS 권한,
분기/인터럽트 조합의 증거를 이 검사로 대신하지 않는다.

### 다섯 모드의 FP 상태 접근과 host/guest Dirty

기준은 [H 1.0의 `vsstatus`](https://docs.riscv.org/reference/isa/v20260120/priv/hypervisor.html)와
[특권 1.13의 FS](https://docs.riscv.org/reference/isa/priv/machine.html)다. V=1에서는
host와 guest FS가 함께 적용되고 어느 한쪽이 Off이면 illegal instruction이다.
FP 상태를 변경하면 두 FS가 Dirty가 된다. V=0에서는 guest FS가 일반 FP 접근의
허용 여부에 영향을 주지 않는다.

`python scripts/run_fp_permission_matrix.py`는 host FS 0~3 × guest FS 0~3 ×
11종의 명령을 M/HS/VS/U/VU에서 실행한다. 모드별 같은 ELF를 Sail과 전체
H/V SoC에 사용하며 총 880개 probe의 허용 결과와 정확한 trap을 확인한다.

| 조건 | 실행 검사 |
|---|---|
| FP 진입 경로 | FADD.D, FMADD.D, FLD/FSD, FMV.D.X/FMV.X.D, FCSR/FRM/FFLAGS read, FCSR/FFLAGS write |
| FS-Off | 거부 시 cause 2·정확한 PC·원본 instruction tval과 writeback 없음. cause 22로 바꾸는 오류를 거부 |
| 허용 결과와 상태 보존 | M trap 뒤 FPR 목적지·정수 목적지·FCSR·SRAM 값을 확인. 거부된 명령은 초기 데이터를 보존 |
| 실제 상태 변경의 Dirty | FPR을 다른 값으로 덮어쓰거나 FCSR을 실제로 바꾼 허용 사례에 한해 host FS=3·SD=1을 재활성화 전에 확인. V=1이면 guest FS=3·guest SD=1도 확인 |
| 읽기 전용 명령의 Dirty | imprecise Dirty가 허용되므로 읽기 전용 명령이 Clean을 유지해야 한다고 가정하지 않음 |
| trap 복귀 | 각 probe 뒤 모드에 맞는 ECALL을 확인하고 MRET으로 실패 지점 이후에 복귀. FS-Off 접근·ECALL은 모두 M으로 직접 전달하도록 구성 |

880개 중 허용 594개·FS-Off 거부 286개와 ECALL을 포함한 정확한 trap
1,166개를 통과했고, 모드별 같은 ELF의 Sail/RTL 이벤트 합계 80,525건이
일치했다. host Dirty readback 324개·guest Dirty readback 108개를 확인했다.
cause/tval 및 Dirty 상태를 바꾼 trace 대조군 117개를 독립 검사기가 거부했다.
이 대조군은 변경 RTL 실행이 아니다. 예상 case table, ELF·trace·로그·현재 RTL/model·Sail·생성기와 helper 해시를
`out/rva23/fp_permission_matrix/`의 개별 보고서와 상위 `report.json`에 연결한다.
`--check`는 ELF를 재빌드하지 않고 이 근거를 재검사한다. 이 유한 Bare
matrix는 delegation, 페이지/PMP fault와 FP 상태 권한의 동시 조합 및 모든
스케줄을 대신하지 않는다.

### FP 상태·정확한 예외와 분기 취소

기준은 [특권 1.13의 extension context 상태](https://docs.riscv.org/reference/isa/priv/machine.html)다.
FS=Off의 상태 접근은 illegal instruction이며 FS 설정 변경이 기존 FP
레지스터를 지우지는 않는다. 규격은 보수적·추측적 Dirty 갱신도 허용한다.
따라서 Dirty의 정밀 추적 정책과 취소된 명령의 데이터·flags 유출을 구분한다.

현재 backend는 `retire_fire`로 FP destination write와 flags 누적을 CSR에
전달한다. `rv_fpu_rva23`은 더 젊은 owner를 flush하면 결과 valid를 막고
slow datapath를 reset한다. 다음 근거를 통합 요구사항 감사에 연결했다.

| 검토 조건 | 실행 근거 |
|---|---|
| M 모드 FS/SD | `audit_fp_state_contract.py`가 기존 전체 H/V replay의 readback 5건을 확인. VS=XS=0에서 FS가 Initial/Dirty/Clean/Dirty/Dirty, SD가 Dirty에 대응. FCLASS가 Clean을 유지하는 것은 현재 정책 |
| FS-Off와 예약 rm | FS-Off의 arithmetic·load·store·raw move·FCSR 접근 5건과 예약 static/dynamic rm 2건에서 cause 2·원본 mtval·writeback 없음. 예약 rm의 illegal trap은 현재 구현 선택 |
| 잘못된 경로의 FP | `run_fp_branch_order.py`의 8개 대표 명령이 실제 dispatch됨. 그중 목표 FP 요청 5건 수락, 4건 완료 후 취소. dependency-chain의 중간 FP 요청은 이 대표 명령 수와 별개 |
| 실행 중 FDIV 취소 | dependency-chain 뒤 FDIV가 SLOW 상태인 동안 flush를 관찰. 다음 cycle에 IDLE 및 결과 valid 없음, 이후 정상 FADD와 새 FDIV의 결과 확인 |
| 보호되는 상태 | FP·정수 결과, flags와 SRAM 보존. wrong-path FP store·bad load·FS-Off 명령은 retire/trap하지 않음. FS Off→Initial에서 FP 데이터와 `fflags=5` 유지 |

분기 fixture는 같은 ELF로 Sail·기본 RTL·관찰 RTL의 이벤트 409개가 각각
일치했다. 관찰 wrapper는 production RTL을 수정하거나 신호를 강제하지
않으며 두 모델의 RTL 입력 해시를 대조한다. 목표 PC/sequence의 수락·완료·
flush 및 slow 상태를 관찰해 단지 명령이 실행되지 않은 경우와 구분한다.
요청/복구/kill witness 누락 대조군 3개와 기존 상태 trace 대조군 19개를
거부했다. 대조군은 변경 RTL 실행이 아니다. 근거는
`out/rva23/fp_branch_order/report.json`과 `out/rva23/fp_state_contract_audit.json`이다.
이 유한 M 모드 검사는 모든 guest FS·권한·interrupt·schedule 조합을 대신하지 않는다.

### F/D/Zfhmin 메모리와 half raw 이동

기준은 [F 2.2](https://docs.riscv.org/reference/isa/v20260120/unpriv/f-st-ext.html),
[D 2.2](https://docs.riscv.org/reference/isa/v20260120/unpriv/d-st-ext.html),
[Zfhmin 1.0](https://docs.riscv.org/reference/isa/unpriv/zfh.html) 및
[C 2.0](https://docs.riscv.org/reference/isa/unpriv/c-st-ext.html)이다.
FP 메모리는 decode·FP PRF·LSU/assist·cache 경로로 연결되고, 압축 D 메모리는
`rv_c_expander`에서 일반 D 메모리 명령으로 확장된다. half raw 이동은
`rv_fpu_rva23`의 bit-preserving 경로를 사용한다.

`python scripts/run_fp_memory_contract.py`는 12형식의 probe 688개를 폭별
같은 ELF로 Sail과 전체 H/V SoC에 실행한다. ELF의 file-backed 바이트와
실제 retire 순서의 정수/FP store로 독립 메모리를 구성한다. 초기화되지 않은
NOBITS를 0으로 가정하지 않는다.

| 조건 | 실행 검사 |
|---|---|
| FLH/FLW/FLD | NaN payload를 포함한 비트 보존과 H/S boxing. 목적지를 읽을 값의 보수로 미리 채워 실제 덮어쓰기를 확인 |
| FSH/FSW/FSD | 상위 입력 비트·잘못된 boxing을 무시하고 하위 16/32/64비트만 저장. FP source도 그대로 보존 |
| 압축 D 메모리 | C.FLD/C.FSD/C.FLDSP/C.FSDSP의 zero-offset 형식에서 base/SP를 바꿔 같은 접근을 검사. nonzero offset은 이 fixture 범위가 아님 |
| 비정렬·경계 | 정상 SRAM에서 8개 주소 배치로 비정렬 접근과 64B 라인·4KiB 페이지 경계를 포함. 페이지 변환은 사용하지 않음 |
| store 관찰 | 각 FP store 뒤 주변 32바이트를 정수 LD 네 번으로 확인. 320개 쓰기의 모든 바이트와 인접 guard를 검사 |
| FMV.H.X / FMV.X.H | NaN payload 보존, FP 목적지 boxing과 정수 목적지 부호 확장. 잘못된 boxing도 raw 이동에서는 그대로 사용 |
| flag 상태 | 초기 `fflags=0/5/31`에서 보존을 확인 |

H 176개·S 128개·D 384개가 통과했고 같은 ELF의 Sail/RTL 이벤트 합계
44,936건이 일치했다. 비정렬 432회·라인 경계 208회·페이지 경계 80회를
확인했다. 결과/후속 load 및 flag를 바꾼 trace 대조군 24개를 독립 검사기가
거부했다. 대조군은 변경 RTL 실행이 아니다. ELF·trace·로그·현재 RTL/model·Sail·
생성기와 helper 해시는 `out/rva23/fp_memory_contract/`의 개별 보고서와
상위 `report.json`에 연결하며 `--check`로 재검사한다. bus 원자성·순서·
외부 writer 동시성, 변환/권한 fault와 FS/pipeline 경합은 별도 검사 범위다.

### F/D 산술과 FMA의 단일 반올림

기준은 [F 2.2의 산술](https://docs.riscv.org/reference/isa/v20260120/unpriv/f-st-ext.html)과
[D 2.2](https://docs.riscv.org/reference/isa/v20260120/unpriv/d-st-ext.html)다.
`rv_fp_format`은 HardFloat add/mul/FMA와 iterative div/sqrt를 사용한다.
`rv_fpu_rva23`은 format·rounding·결과 tag 및 slow owner를 관리하고
ROB에서 결과·flags를 commit한다. `python scripts/run_fp_arithmetic_contract.py`는
18형식의 probe 2,700개를 배치별 같은 ELF로 Sail과 전체 H/V SoC에서 실행한다.
예상값은 `fp_reference.BinaryFP`의 정확한 유리수와 정수 제곱근 계산이며
호스트 부동소수점 연산을 사용하지 않는다.

| 조항 | 실행 검사 |
|---|---|
| ADD/SUB/MUL/DIV/SQRT.S/D | ±0·정상/비정규 수·무한대·qNaN/sNaN, 취소·inexact·overflow·underflow·0 나누기·음수 sqrt |
| 정적·동적 반올림 | 다섯 모드 각각. 정적 모드에서는 `frm`을 다른 값으로 설정 |
| 예외 누적 | 결과마다 flags를 읽는다. 기본 산술 배치에서 NV/DZ/OF/UF/NX 모두 실제 발생했고 FMA 배치에서는 NV/OF/UF/NX를 확인 |
| 네 FMA의 부호 | FMADD/FMSUB/FNMSUB/FNMADD의 product·addend 부호, signed zero와 무한대 조합 |
| FMA 단일 반올림 | `(1+2⁻ᶠ)(1−2⁻ᶠ)−1`의 RNE 결과는 `−2⁻²ᶠ`(f=23/52). 곱셈을 먼저 반올림한 결과 0을 잘못된 trace 결과로 거부 |
| FMA 예외 경계 | 곱셈만 하면 overflow지만 융합 결과는 유한한 취소 사례, `∞×0+qNaN`의 NV 발생 |

S/D 각각 기본 산술 750개·FMA 600개가 통과했고 배치별 같은 ELF의
Sail/RTL 이벤트 합계 54,330건이 일치했다. 결과·각 flag 변경 및 split
multiply/add 반올림 대조군 110개를 독립 검사기가 거부했다. 대조군은
변경 RTL 실행이 아니다. ELF·trace·로그·현재 RTL/model·
Sail·생성기와 oracle/helper 해시는 `out/rva23/fp_arithmetic_contract/`의
개별 보고서와 상위 `report.json`에 연결한다. `--check`는 ELF 재빌드 없이
근거를 재검사한다. 전 입력, 예약 rounding mode, FS 권한과 speculative
flush/owner 경합은 이 검사의 완료 범위로 확대하지 않는다.

### S/D/H 포맷 변환과 직접 반올림

기준은 [D 2.2](https://docs.riscv.org/reference/isa/v20260120/unpriv/d-st-ext.html)와
[Zfhmin 1.0](https://docs.riscv.org/reference/isa/unpriv/zfh.html)이다.
`rv_fp_convert`는 소스별 boxing을 확인하고 각 소스·목적지 조합의
HardFloat `recFNToRecFN`으로 직접 변환한다. 목적지 정밀도에서 한 번
반올림하며 S/H 결과의 상위 비트를 모두 1로 채운다.

`python scripts/run_fp_format_contract.py`는 S↔D·H↔S·H↔D 여섯 변환의
probe 1,600개를 목적지별 같은 ELF로 Sail과 전체 H/V SoC에서 실행한다.
예상값·flags는 `fp_reference.BinaryFP`의 정확한 유리수 모델을 사용한다.

| 조건 | 실행 검사 |
|---|---|
| 반올림 선택 | 다섯 정적·동적 모드. 정적 모드는 `frm`을 다르게 설정 |
| 폭을 줄이는 변환 | 최소 subnormal의 절반·1.5배, 최소 normal 경계, 최대 finite 및 overflow의 절반 ULP, ±1 근처의 tie와 이웃 표현값 |
| 특수값·boxing | ±0·비정규 수·무한대·qNaN/sNaN, 잘못된 S/H boxing의 canonical NaN 처리와 결과 boxing |
| 예외 상태 | NX/UF/OF/NV 및 초기 flags의 보존·누적을 각 probe 후 확인 |
| 직접 D→H | 입력 `0x3ff0020000000001`의 RNE 결과는 H `0x3c01`. S를 거치는 이중 반올림은 `0x3c00`으로 달라지며 이를 잘못된 결과로 거부 |

S 목적지 530개·D 목적지 330개·H 목적지 740개가 통과했고 같은 ELF의
Sail/RTL 이벤트 합계 23,178건이 일치했다. 결과·flag를 바꾼 trace 대조군
30개와 이중 반올림 대조군 1개를 독립 검사기가 거부했다. 이 대조군은
변경 RTL 실행이 아니다. ELF·trace·로그·현재 RTL/model·Sail·생성기·oracle/helper 해시는
`out/rva23/fp_format_contract/`의 개별 보고서와 상위 `report.json`에 연결한다.
`--check`는 ELF를 다시 만들지 않고 이를 재검사한다. half 메모리/이동,
산술, 예약 rounding mode, FS 권한과 pipeline 경합은 별도 범위다.

### F/D와 정수 사이의 변환·반올림

기준은 [F 2.2의 변환·반올림](https://docs.riscv.org/reference/isa/v20260120/unpriv/f-st-ext.html)과
[D 2.2](https://docs.riscv.org/reference/isa/v20260120/unpriv/d-st-ext.html)다.
`rv_fp_decode_pkg`는 W/WU/L/LU selector와 rounding 필드를 선택한다.
`rv_fpu_rva23`이 동적 `frm`을 고르고 `rv_fp_format`의 HardFloat 정수 변환
경로로 전달한다. W/WU 정수 결과는 모두 64비트로 부호 확장한다.

`python scripts/run_fp_integer_contract.py`는 두 포맷에서 각각 같은 ELF를
Sail과 전체 H/V SoC에 실행한다. 16형식의 probe 2,760개(S 1,400개·D
1,360개)를 기존 `fp_reference.BinaryFP`의 정확한 유리수 계산으로 검사한다.
호스트 float 계산은 사용하지 않는다.

| 조건 | 실행 검사 |
|---|---|
| 정적·동적 반올림 | RNE/RTZ/RDN/RUP/RMM 각각을 직접 지정하거나 `rm=7`과 `frm`으로 지정. 정적 경로에서는 `frm`을 다른 값으로 설정 |
| 정수 입력 폭 | W/WU의 상위 32비트 무시, 부호·비부호 입력과 L/LU의 64비트 경계. 2²⁴·2⁵³ 주변의 inexact/tie 입력 |
| 정수 결과 폭 | W/WU의 RV64 부호 확장, L/LU의 64비트 결과 |
| 변환 범위·예외 | ±0, half-integer ties, 정수 경계와 직전 표현값, NaN·무한대·잘못된 S boxing. 포화 결과와 NV/NX 및 기존 flags 누적을 확인 |

형식별 결과·NX·NV를 바꾼 trace 대조군 48개를 독립 검사기가 거부했다.
포맷별 같은 ELF의 Sail/RTL 이벤트는 S 18,284건·D 18,290건이 일치했다.
각 포맷의 ELF·trace·로그·RTL/model·Sail·생성기와 oracle/helper 해시는
`out/rva23/fp_integer_contract/`의 개별 보고서와 상위 `report.json`에
연결한다. `--check`는 ELF 재빌드 없이 이를 재검사하며 통합 감사에 포함된다.
느린 호스트의 재실행은 `RV23_HOST_TIMEOUT_SCALE=2`로 관찰 시간을 늘릴 수 있다.
S/D/H 포맷 간 변환, 예약 rounding mode, FS 권한과 pipeline 경합은 별도 범위다.

### F/D의 비교·min/max와 NV 누적

기준은 [F 2.2](https://docs.riscv.org/reference/isa/v20260120/unpriv/f-st-ext.html)와
[D 2.2](https://docs.riscv.org/reference/isa/v20260120/unpriv/d-st-ext.html)다.
`rv_fpu_rva23`의 S 입력 unbox 이후 `rv_fp_format`은 HardFloat 비교 결과와
직접적인 min/max 선택을 사용한다. 결과 flag는 ROB를 거쳐 기존 `fflags`에
누적된다. `python scripts/run_fp_compare_contract.py`는 같은 ELF를 Sail과
전체 H/V SoC에서 실행하고 10형식의 probe 1,215개를 검사한다.

| 조건 | 실행 검사 |
|---|---|
| FEQ.S/D | ±0은 같으며 NaN이면 false. signaling NaN만 NV를 추가 |
| FLT/FLE.S/D | NaN이면 false이며 quiet/signaling NaN 모두 NV를 추가 |
| FMIN/FMAX.S/D | 한 NaN이면 비NaN 입력, 두 NaN이면 canonical NaN. signaling NaN은 NV를 추가 |
| ±0 및 수의 순서 | min은 −0, max는 +0. 부호·지수·가수의 비트 표현으로 정수 순서를 계산하고 호스트 float 계산을 사용하지 않음 |
| boxing 및 flag 상태 | 잘못된 S boxing 75개 probe와 초기 `fflags=0/5/31`을 포함. 기존 flag 보존 및 필요한 NV 누적을 각 probe 후 확인 |

잘못된 결과 10개, NV의 불필요한 추가 10개와 누락 10개의 trace 대조군을
독립 검사기가 거부했다. 이 대조군은 변경 RTL 실행이 아니다.
ELF·로그·trace·현재 RTL/model·Sail·생성기 및 helper 해시는
`out/rva23/fp_compare_contract/report.json`에 연결한다. `--check`는 저장된
근거를 재검사하며 통합 요구사항 감사에도 포함한다. 반올림 산술·FS 권한과
pipeline 경합 검증을 대신하지 않는다.

### F/D의 분류·부호·레지스터 이동

기준은 [F 2.2](https://docs.riscv.org/reference/isa/v20260120/unpriv/f-st-ext.html)와
[D 2.2의 NaN boxing](https://docs.riscv.org/reference/isa/v20260120/unpriv/d-st-ext.html)이다.
`rv_fpu_rva23`은 S 연산 입력의 boxing을 검사하고 raw move는 그 검사를
우회한다. `rv_fp_format`의 분류·부호·이동 결과는 일반 FP result/WB 경로로
전달된다. S 결과의 FP 목적지는 상위 32비트를 모두 1로 채운다.

`python scripts/run_fp_bit_contract.py`는 같은 ELF를 Sail과 전체 H/V SoC에서
실행하고 다음 12형식의 probe 1,110개를 독립 정수·비트 계산으로 검사한다.

| 조건 | 실행 검사 |
|---|---|
| FCLASS.S/D | 양·음의 정상/비정규 수·0·무한대와 signaling/quiet NaN의 분류 10종 |
| FSGNJ/N/X.S/D | 두 입력의 부호 조합, NaN payload 보존, 정상 boxing과 malformed S 입력의 canonical NaN 처리 |
| FMV.W.X / FMV.X.W | 하위 32비트 이동, FP 목적지 boxing, 정수 목적지 부호 확장. 잘못된 boxing도 raw move에서는 원본 하위 비트를 보존 |
| FMV.D.X / FMV.X.D | NaN payload를 포함한 64비트 원본 보존 |
| 부동소수점 예외 상태 | 각 probe 전 `fflags=0/5/31`을 쓰고 이후 값이 동일한지 확인. 새로운 NV 설정과 기존 flag 소실 모두 검사 |

잘못된 결과 12개와 flag 설정·삭제 2개의 trace 대조군을 독립 검사기가
거부했다. 이 대조군은 변경 RTL 실행이 아니다. 실행·ELF·trace·현재 RTL 및
Sail·생성기 해시를 `out/rva23/fp_bit_contract/report.json`에 묶는다.
`--check`는 저장된 같은 ELF와 기록을 재검사하며 통합 요구사항 감사에도
포함한다. 산술 결과·반올림·FS 권한·flush와 FP owner 경합은 이 검사의
완료 범위로 확대하지 않는다.

### RV64 A의 값과 메모리 갱신 검토

기준은 [A 2.1의 AMO와 LR/SC 조항](https://docs.riscv.org/reference/isa/v20260120/unpriv/a-st-ext.html)이다.
atomic head가 순서·번역·권한을 확인하고 `rv23_atomic_engine`이 전용 AXI
exclusive ID로 읽기·계산·쓰기를 수행한다. W형은 하위 32비트로 계산하고
이전 값을 부호 확장해 돌려준다. bridge의 exclusive monitor와 snoop가
충돌한 접근을 처리하며 AMO 쓰기 응답 실패 시 재시도 경로가 있다.

`python scripts/audit_rv64a_contract.py`는 같은 전체 H/V SoC와 Sail의
ELF 19개에서 다음 유한 실행 범위를 검사한다.

| 조항 | 독립 계산·실행 근거 |
|---|---|
| 9가지 AMO의 W/D 계산 | ELF의 file-backed 바이트와 선행 store로 메모리를 구성한다. 실제 rs1/rs2를 복원하고 ADD/SWAP/XOR/OR/AND/MIN/MAX/MINU/MAXU를 계산한다. |
| 이전 값 반환·W형 확장 | AMO 42회 중 rd=x0인 1회를 제외한 41개 이전 값을 확인한다. W형은 상위 rs2 비트가 0이 아닌 입력과 음수인 이전 값을 포함한다. |
| 메모리 갱신과 rd=x0 | rd=x0도 쓰기를 생략하지 않는다. AMO 갱신 42회 모두 후속 일반 load가 전 바이트를 관찰했다. 초기 NOBITS를 0이라고 가정하지 않는다. |
| LR/SC.W | LR 1,025회, SC 성공 1,025회·실패 3회. 성공에는 최근 LR의 주소·폭 일치를 요구하고 SC 시도 뒤 예약을 소비한다. 실패는 허용되는 관찰 결과로 사용하며 항상 성공해야 한다고 가정하지 않는다. |

AMO/LR 반환값과 일반 load의 잘못된 결과를 넣은 trace 대조군을 각각
19개씩 거부했다. 이 대조군은 변경 RTL 실행이 아니다. ELF·로그·trace와
현재 RTL/model 및 감사기의 해시를 `out/rva23/rv64a_contract_audit.json`에
묶고 통합 감사에서 재검사한다. 이 값 검사는 aq/rl의 순서, 외부 writer와의
원자성, fault, LR/SC.D 및 진행성의 증명이 아니다. 해당 조건은 기존
`run_fence_order.py`, atomic/guest replay, debug reservation과 LR/SC
진행성 테스트의 별도 범위로 유지한다.

### RV64 B 및 Zicond 계산 의미 검토

기준은 [B 1.0.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/b-st-ext.html)과
[Zicond 1.0.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zicond.html)이다.
`rv_ooo_pkg.decode_bitmanip`이 인코딩·즉시값·word 동작을 선택하고,
`rv_int_alu`가 계산하며 일반 정수 issue/result/WB/retire 경로로 전달한다.

| 조항 | RTL 연결과 독립 계산의 범위 |
|---|---|
| Zba의 shift/add와 `.uw` | 8형식. `.uw`의 rs1 하위 32비트를 zero-extend한 뒤 XLEN 계산 |
| Zbb의 논리·count·min/max·확장 | 부호/비부호 비교, 0의 CLZ/CTZ, byte/half 확장과 word count |
| Zbb의 rotate·byte 연산 | 32/64비트 rotate와 word 결과 부호 확장, OR-combine·byte reverse. rotate는 Python 비트열 순환으로 계산 |
| Zbs의 bit 조작 | register/immediate 8형식, 마스킹된 index의 bit clear/extract/invert/set |
| Zicond의 조건부 zero | 두 형식 각각 rs2=0 및 비0 실행 확인 |

`python scripts/audit_rv64b_contract.py`는 기존 전체 H/V SoC와 Sail의 같은
ELF 42개에서 trace·로그·ELF·현재 RTL/model 해시를 확인한다. 앞선 정수
writeback으로 실제 입력을 복원했다. retire 1,810건 중 x0 목적지 31건은
결과값 관찰에서 제외했고 나머지 결과 1,779개를 독립 계산했다. 각 형식의
결과를 바꾼 trace 대조군 42개를 모두 거부했다. 이 대조군은 감사기의
검출력을 확인하며 변경 RTL 실행은 아니다. 근거는
`out/rva23/rv64b_contract_audit.json`이며 통합 감사에 포함한다.
기존 `scalar/bitmanip` H/V replay의 246개 결과도 독립 계산으로 검사했다.
이 별도 fixture는 CLZW/CTZW/CPOPW에서 상위 32비트가 0이 아닌 입력과
0 입력을 포함해 upstream trace의 빈틈을 보완하며 추가 Sail 대조로 표시하지 않는다.
유한한 적법 명령 실행 범위로, 모든 입력·예약 인코딩·권한·flush/stall 조합의
증명이나 전체 프로파일 인증을 뜻하지 않는다.

### RV64M 곱셈·나눗셈 의미 검토

기준은 [M 2.0의 곱셈·나눗셈 조항](https://riscv.github.io/riscv-unified-db/manual/html/isa/isa_20240411/chapters/m-st-ext.html)이다.
`python scripts/audit_rv64m_contract.py`는 현재 H/V SoC에서 실행한
`rv64um` ELF 13개의 retire trace를 읽고 앞선 정수 writeback으로
각 명령의 실제 입력을 복원한다. Python의 정수 곱셈·절댓값 나눗셈으로
RTL 결과 296개를 계산해 비교하며, 같은 trace의 Sail 대조도 재실행한다.
각 명령 종류에서 결과 한 비트를 바꾼 13개 대조군을 모두 거부한다.

| 조항 | RTL 경로 | 확인한 실행 근거 |
|---|---|---|
| MUL의 하위 XLEN 비트 | multiplier의 `MUL_LOW` 선택 | `mul` 47회 |
| MULH/MULHSU/MULHU의 부호별 상위 곱 | multiplier의 부호 보정과 상위 64비트 선택 | 각각 43/43/45회 |
| MULW의 하위 32비트 곱과 부호 확장 | multiplier의 `word_operation` 선택 | 43회, 상위 입력 비트가 0이 아닌 사례 포함 |
| DIV/REM의 0 방향 몫 및 피제수와 같은 나머지 부호 | divider의 절댓값 반복과 결과 부호 적용 | DIV/DIVU 10/9회, REM/REMU 9/9회 |
| 0으로 나눌 때 전부 1인 몫과 원래 피제수인 나머지 | divider의 `divide_by_zero` 경로 | W형을 포함한 나눗셈·나머지 8종 모두에서 확인 |
| signed 최솟값÷−1의 몫과 0인 나머지 | divider의 `signed_overflow` 경로 | DIV/REM/DIVW/REMW 모두에서 확인 |
| W형 입력의 하위 32비트 사용과 항상 부호 확장되는 결과 | divider의 effective operand 및 최종 word 선택 | DIVW/DIVUW 10/9회, REMW/REMUW 10/9회; 상위 입력 비트가 0이 아닌 사례 및 0 나누기 포함 |

이 표는 M의 해당 산술 조항을 구현과 실행에 연결한다. 전 피연산자 공간,
모든 pipeline stall/flush 조합 또는 전체 프로파일의 증명은 아니다.
ELF·trace·로그·현재 RTL/model 및 참조 실행 파일 해시를 검사하고
`out/rva23/rv64m_contract_audit.json`에 근거를 남긴다. 통합 요구사항 감사에도 포함된다.

### RV64I 정수 계산·제어 흐름 검토

기준은 [기본 정수 명령 조항](https://riscv.github.io/riscv-unified-db/manual/html/isa/isa_20240411/chapters/rv32.html)과
[RV64I의 차이](https://riscv.github.io/riscv-unified-db/manual/html/isa/isa_20240411/chapters/rv64.html)다.
`python scripts/audit_rv64i_compute_control.py`는 현재 H/V SoC의 기존
`rv64ui` ELF 38개에서 정수 피연산자를 복원하고 독립 정수·PC 계산을 적용한다.
초기화를 포함해 계산·제어 명령 6,252개를 검사했다. 목적지가 x0이 아닌
연산은 writeback과 목적지 번호를, 뒤의 trace 행이 있는 각 명령은 다음 PC를
확인했다. 각 ELF의 대상 명령을 합치면 1,475개이며 전체 검사 수에 포함된다.
같은 ELF의 Sail trace도 대조했고 결과·다음 PC의 잘못된 변경 38개를 거부했다.

| 조항 | RTL 근거 | 실행 검사 |
|---|---|---|
| ADD/SUB, 논리 연산, signed/unsigned 비교 및 immediate 부호 확장 | decoder의 OP/OP-IMM과 int ALU의 정수 결과 | Python의 전체 정수 계산 뒤 64비트 절단 및 signed/unsigned 비교 |
| W형의 하위 32비트 결과와 부호 확장 | OP-32/OP-IMM-32 및 ALU word 결과 선택 | ADDW/SUBW/ADDIW와 여섯 W shift의 결과 |
| 레지스터 shift의 하위 5/6비트 및 arithmetic shift | int ALU의 full/word shift | 전체·W형의 register/immediate shift 결과 |
| LUI/AUIPC의 32비트 즉시값 부호 확장과 PC 합성 | decoder의 U-immediate 및 ALU | 결과 레지스터와 다음 PC |
| 조건 분기, JAL/JALR의 대상과 link | branch unit의 비교·대상·link 경로 | BEQ/BNE/BLT/BGE/BLTU/BGEU 각각 양쪽 조건, jump 대상 및 x0 이외 link writeback |

이 검토는 적법한 정수 계산·제어 명령의 유한 실행 범위다. load/store,
FENCE, ECALL/EBREAK, 예약 인코딩, 비정렬 trap 및 모든 pipeline 스케줄의
검증은 각각의 별도 근거를 사용한다. JALR 대상의 bit 0 제거는 RTL과
oracle에서 확인하지만 이 표만으로 모든 주소 경계 입력을 실행했다고
주장하지 않는다. 감사 결과는 `out/rva23/rv64i_compute_control_audit.json`이며
현재 소스·실행 파일·ELF·로그·trace 해시에 묶여 통합 감사에 포함된다.

### RV64I load/store 값 검토

`python scripts/audit_rv64i_memory_values.py`는 LB/LBU/LH/LHU/LW/LWU/LD와
SB/SH/SW/SD의 ELF 11개 및 `ld_st`·`st_ld`·`ma_data`를 검사한다.
ELF64의 file-backed PT_LOAD 바이트를 초기 메모리로 읽고, retire 순서의
store를 little-endian 바이트 모델에 적용한다. 쓰기 전 NOBITS 영역을
임의로 0이라고 가정하지 않으며, load의 모든 바이트가 초기 ELF나 선행
store에서 알려져 있어야 한다. 중간에 실행한 C.LW/C.LD/C.SW/C.SD와
각 SP형도 원본 16비트 인코딩에서 해석한다.

| 조항 | RTL 근거 | 확인한 실행 범위 |
|---|---|---|
| rs1+signed immediate의 유효 주소 | decoder와 LSU 주소 경로 | 복원한 정수 레지스터와 I/S immediate로 바이트 주소 계산 |
| byte/half/word load의 signed/unsigned 확장과 LD | LSU `format_load_data` 및 비정렬 assist | load 831회의 값 확인; x0 목적지는 결과값 관찰 범위에서 제외 |
| store의 크기와 하위 데이터·부분 쓰기 | LSU store strobe/forward 및 assist 경로 | store 760회를 바이트 모델에 적용하고 그중 618회의 일부 또는 전체 바이트를 후속 load에서 관찰 |
| 메모리 byte 순서와 비정렬 값 | LSU 및 head memory assist | 전체 1,591개 메모리 명령 중 비정렬 268회 |

Sail과 같은 ELF의 trace를 대조한 후 독립 바이트 계산을 적용한다.
load 결과를 바꾼 14개와 첫 store의 주소를 한 바이트 옮긴 네 trace
대조군을 거부했다. 이 대조군은 감사기의 검출력을 확인하며 수정된
RTL을 실행한 결과가 아니다. 버스 요청 수·순서, 읽히지 않은 store
바이트, 예외와 동시 접근은 기존 별도 검사 범위다. 결과는
`out/rva23/rv64i_memory_value_audit.json`에 남기고 통합 요구사항 감사에 포함한다.

`run_profile_csr_geometry.py --compare-before out/rva23/hgatp_warl_before`는
보관한 ELF를 수정 전후의 SoC에서 그대로 재실행한다. 두 모델의 RTL
입력 해시에서 `rv_hypervisor_csrs.sv`만 다른 것을 확인한 뒤 비교한다.
수정 전 실패 사례 218과 수정 후 통과를 담은 해시와 로그는
`out/rva23/hgatp_warl_comparison/report.json`에 있다.

`run_guest_ifetch_inval.py`는 동일한 두 게스트 가상 주소에서 실제 코드를
실행한다. HS는 `HINVAL.GVMA`와 `HINVAL.VVMA`를 사용해 각 단계의 매핑을
갱신한다. 마지막에는 VS가 자기 PTE를 수정하고 `SINVAL.VMA`를 실행한다.
세 경우 모두 `SFENCE.W.INVAL`과 `SFENCE.INVAL.IR` 사이에 두 주소의
무효화를 배치했다. `VMIDLEN=0`과 ASID 9로 실행해 최초 fetch를 포함한
여덟 결과를 확인했다. 수정 후 RTL과 해당 VMID 폭으로 구성한 Sail의
동일 ELF 실행 이벤트 2,880개가 일치했다. [Svinval 규격](https://docs.riscv.org/reference/isa/v20240411/priv/svinval.html)

`run_guest_vector_segment_ff.py`는 `VLSEG2E32FF`의 페이지 경계 사례를
게스트에서 실행한다. VS-stage와 G-stage의 leaf를 각각 비워 두고 8개 사례를
확인했다. 첫 segment의 두 번째 필드가 실패하면 `vl=4`와 `vstart=0`을
유지한 채 HS에 예외를 전달했다. 핸들러는 `sepc`와 `stval`, G-stage의
shifted `htval`을 검사한 뒤 해당 PTE를 복구했고 같은 PC에서 완료됐다.
뒤쪽 segment의 fault는 예외 없이 `vl`을 segment 인덱스로 줄였다. 첫
segment를 마스크한 경우에도 인덱스 1의 fault가 `vl=1`을 남겼다. 완료된
segment 값과 마스크된 목적지를 검사했으며, 동일 ELF의 Sail·RTL 실행
이벤트 2,987개가 일치했다. [V 규격](https://docs.riscv.org/reference/isa/unpriv/v-st-ext)

`run_guest_vector_segment_ff.py --whole-register`는 `vill=1`, `vl=0`에서
`VL4RE64`와 `VS4R`로 네 레지스터를 복원·저장했다. VS-stage와 G-stage에서
각각 load·store가 페이지 경계에서 트랩했고, 핸들러는 EEW에 따라 `vstart=4`
또는 `32`와 `sepc`·`stval`·`htval`을 확인했다. 이미 처리된 앞 32바이트를
재실행 전에 바꿔 둔 뒤, 같은 PC에서 재개했을 때 그 부분을 다시 읽거나
쓰지 않는지 검사했다. Sail과 RTL이 동일 ELF에서 3,467개 이벤트에 일치했다.
[V 1.0 전체 레지스터 저장·복원](https://docs.riscv.org/reference/isa/v20240411/_attachments/riscv-unprivileged.pdf)

`scripts/run_zvbb_native.py`는 ACT4의 생성 벡터 시험에 별도 항목이 없는
Zvbb의 16개 형식을 같은 ELF로 Sail과 전체 RV64 SoC에서 실행한다.
SEW 8/16/32/64의 LMUL=2 사례에 합법적인 분수 LMUL 조합 6개를 더해
471건을 확인했다. 일반 실행, 마스크와 `vstart=1`, `vl=0`의 목적지
레지스터에서 읽은 64비트 값 3,768개를 예상값과 대조했다.
`vstart` 초기화, 명령 인코딩과 마스크 비트를 검사했으며 두 모델의
실행 이벤트 30,809개가 일치했다. [Zvbb 규격](https://docs.riscv.org/reference/isa/v20250508/unpriv/vector-crypto.html)

`scripts/run_guest_superpages.py`는 실제 H/V SoC에서 VS-stage Sv39와
G-stage Sv39x4의 2 MiB·1 GiB leaf를 각각 사용한다. 두 오프셋의 `HLV.D`와
네 `HSV.D`가 정상 완료했다. 네 PTE의 낮은 PPN 비트를 설정했을 때 VS는
load/store page fault 13/15, G-stage는 load/store guest-page fault 21/23을
냈다. HS 핸들러가 `sepc`, `stval`, `htval`, `htinst`, `GVA`를 검사했다.
실패한 저장 이후에도 앞서 쓴 SRAM 값이 보존됐다. G-stage 사례는
Sv39x4 최상위 주소 구간을 사용한다. [Sv39 규격](https://docs.riscv.org/reference/isa/priv/supervisor.html) · [H 확장 규격](https://docs.riscv.org/reference/isa/priv/hypervisor)

`scripts/run_vector_overlap.py`는 RV64 H/V SoC에서 widening의 상위 그룹
겹침, narrowing의 하위 그룹 겹침, 그리고 LMUL=2 소스의 첫 레지스터를
마스크 목적지로 쓰는 세 동작을 확인한다. 마지막 두 동작은 `vstart`를
설정해 재실행하며, 마스크 사례는 `vstart=17`부터 두 번째 레지스터를
읽는 동안 첫 번째 레지스터의 마스크를 갱신한다. 금지된 겹침 다섯 건과
`vstart!=0`인 `vcompress`·`vredsum`은 cause 2를 기록했다. 트랩 처리기가
명령 인코딩과 `mepc`를 확인했고, 복귀 후 `vstart`와 기존 목적지 비트를
대조했다. [RVV 1.0 규격](https://docs.riscv.org/reference/isa/unpriv/v-st-ext)

같은 레지스터를 서로 다른 EEW로 읽는 두 명시적 소스가 겹치면 실행 전에
예외를 낸다. 정수 widening·narrowing, `vrgatherei16`, `vcompress`,
widening reduction·FP, indexed segment store의 일곱 사례를 전체 SoC에서
확인했다. 같은 EEW로 소스를 공유한 덧셈과 indexed store는 실행됐다.
동일 ELF에서 수정 전 `vwaddu.wv`는 retire됐고 수정 후 같은 PC에서
cause 2와 해당 명령 인코딩을 담은 `mtval`을 기록했다.
[RVV 1.0 규격 §31.5.2](https://docs.riscv.org/reference/isa/v20240411/_attachments/riscv-unprivileged.pdf)

`scripts/run_vector_mixed_eew_sail.py`는 mixed-EEW와 예약 메모리
인코딩 사례를 같은 HTIF ELF로 만들어 Sail과 RV64 H/V RTL에서 실행한다.
indexed segment load의 인덱스와 목적지 겹침, 홀수 시작 레지스터,
3개 whole-register 전송, 예약 `mew=1`, 마스크된 `vlm.v`, v31을 넘는
segment 그룹을 추가했다. 예외 13건의 cause 2와 `mtval`, 복귀 직후의
`vstart`를 확인했으며 PC·명령·예외·스칼라 결과 351개가 일치했다.
지정한 벡터 레지스터의 초기 값과 indexed segment store의 목적지
메모리도 보존됐다. [RVV 1.0 벡터 메모리 규격](https://docs.riscv.org/reference/isa/extensions/vector/_attachments/riscv-v-spec.pdf#page=30)

`scripts/run_vector_source_groups_matrix.py`는 벡터 실행 유닛에서 위 소스
겹침 규칙을 10개 명령 형식과 SEW/LMUL 조합에 걸쳐 검사한다. 허용된
레지스터 배치와 예약 인코딩을 포함한 94,734개 패킷이 통과했다. 이 검사는
`vl=0` 설정에서 피연산자 배치에 대한 허용 여부를 대조한다. 결과와 데이터
전송은 위의 전체 SoC 사례에서 확인한다.

`scripts/run_fence_order.py`는 기본 RV64I의 `FENCE RW,RW`, `FENCE.TSO`,
`FENCE IORW,IORW`, 그리고 `fm` 예약값과 0이 아닌 `rs1`·`rd`를 사용한
인코딩을 production RV64 H/V SoC에서 실행한다. 네 경우 모두 ROB head에서
write-through 경로를 기다린 뒤 `SRAM 쓰기 응답 → FENCE retire → 다른
캐시 라인의 읽기 요청` 순서를 지켰다. `FENCE.TSO`는 쓰기 응답 사이클
281, retire 286, 읽기 요청 291을 기록했다. `FENCE W,O`·`I,R`·`O,R`·
`W,I`·`R,O`·`I,W`로 SRAM과 CLINT `MSIP` 사이의 여섯 조합도 실행했다.
LSU 인터페이스에서 선행 접근 응답 → FENCE retire → 후속 접근 요청
순서를 확인했고, 프로그램은 CLINT의 쓰기·읽기 결과를 검사했다. 통합
감사가 테스트벤치, 모델, ELF와 로그 해시를 대조하고 순서를 다시 검사한다.
[RV64I가 상속하는 FENCE 규격](https://docs.riscv.org/reference/isa/v20240411/unpriv/rv32.html)

같은 테스트에 `CBO.ZERO`와 외부 debug AXI 쓰기를 겹치는 사례를 추가했다.
`CBO.ZERO`는 비정렬 주소가 속한 64바이트 라인에 8바이트 쓰기 8회를
냈다. 첫 쓰기는 사이클 1021, 첫 워드를 다시 쓴 debug AXI는 1026,
마지막 zero 쓰기는 1082였다. `CBO.ZERO`와 `FENCE RW,RW`가 차례로
retire한 뒤 벡터 load가 여덟 워드를 요청했다. 벡터와 스칼라가 모두
debug 값을 읽었고, 벡터는 나머지 일곱 워드가 0임을 확인했다. 스칼라는
대상 블록 밖의 양쪽 워드가 보존됐는지도 확인했다.
[Zicboz와 RVWMO](https://docs.riscv.org/reference/isa/unpriv/cmo.html)

같은 계측에서 `AMOADD.D`의 일반·`.aq`·`.rl`·`.aqrl` 네 인코딩과
`LR.D.AQ`·`SC.D.RL`을 실행했다. 세 SRAM 주소를 분리해, 선행 일반
쓰기의 응답이 atomic 엔진 요청보다 먼저 오고 atomic 응답과 retire가
후속 일반 읽기 요청보다 빠른지 확인했다. AMO·LR의 이전 값, SC 성공,
SC가 저장한 최종 값도 검사했다. 이 실행은 현재 코어의 직렬화된 실행을
관찰한 단일 하트 사례다. [A 확장의 순서 규격](https://docs.riscv.org/reference/isa/v20240411/unpriv/a-st-ext.html)

`run_rv64_load_value.py`는 크기가 다른 두 저장이 같은 바이트에 겹치도록
배치하고 두 번째 저장의 주소 또는 값을 `DIVU`로 계산한다. 다음 64비트
워드에도 저장한 뒤 연속 load 여섯 개의 값을 읽는다. 네 저장 폭과 세 위치를
조합한 96개 사례에서 바이트별 최신 저장 값, 부호 확장, 비정렬 캐시 라인
경계를 포함한 load 576개의 결과를 검사했다. 동일 ELF에서 Sail과 RTL의
실행 이벤트 8,578개가 일치했다. 이 실행은 단일 하트의 load 값을 다룬다.
[RVWMO의 Load Value Axiom](https://docs.riscv.org/reference/isa/v20240411/_attachments/riscv-unprivileged.pdf)

같은 시험에서 두 Sv39 가상 주소 범위를 동일한 두 비인접 물리 페이지에
매핑했다. 한 별칭으로 페이지를 걸치는 2·4·8바이트 store를 실행하고,
다른 별칭으로 한 바이트를 덮어쓴 뒤 두 페이지를 읽었다. 페이지를
걸치는 11개 위치마다 나눗셈으로 store 주소 또는 값을 지연시켜 22개를
검사했다. 정렬된 두 load와 경계를 걸치는 비정렬 load가 최신 바이트를
읽었다. 기존 사례를 합쳐 독립 바이트 예상값과 load 708건을 대조했고,
동일 ELF의 Sail·RTL 이벤트 10,095개가 일치했다.
[RVA23 Zicclsm](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html)

`scripts/run_sv39x4_root.py`는 GPA[40:39] 네 조합의 G-stage leaf PTE를 각각
다른 물리 페이지로 바꾼 뒤 `SFENCE.W.INVAL`, 주소 지정 `HINVAL.GVMA`,
`SFENCE.INVAL.IR`을 실행한다. 뒤따르는 `HLV.D` 네 건이 새 페이지의 값을
읽었다. G-stage 매핑을 유지한 상태에서 VS leaf PTE도 변경하고 같은 fence
쌍 사이에 주소 지정 `HINVAL.VVMA`를 실행했다. 변경 전후 같은 GVA의
`HLV.D`는 서로 다른 GPA에서 각각 기대한 값을 읽었다. 계약 감사가 각
결과와 fence, load의 retire 순서를 대조했다.
[Svinval 규격](https://docs.riscv.org/reference/isa/v20240411/priv/svinval.html)

`scripts/run_hypervisor_vector_faults.py --vu`는 두 단계 주소 변환을 사용하는
VU에서 페이지 경계를 넘는 `VSE64.V`와 `VLE64.V`를 실행한다. 두 번째
페이지에서 G-stage fault가 나면 HS 핸들러가 `hstatus.SPV=1`, `SPVP=0`,
`vstart=2`, GVA 및 GPA를 확인하고 PTE를 고친 뒤 같은 PC로 복귀한다.
완료된 메모리 쓰기와 목적지 원소가 보존됐고, 감사에서 VU ECALL 두 건과
각 벡터 명령의 재실행을 retire 기록에서 대조했다.
[H 확장 규격](https://docs.riscv.org/reference/isa/priv/hypervisor)

`scripts/run_split_fetch_faults.py`는 `PC=0x40000ffe`의 32비트 명령 뒤쪽 parcel을 `0x40001000`에서 fault시킨다. HS/VS 실행, M/HS/VS trap 대상, page/access fault와 두 G-stage guest-page fault를 조합한 12개 사례와 24개 trap이 통과했다. 소프트웨어 handler가 xepc, xtval, GVA/MPV/SPV, xRET 복귀를 검사한다. G-stage 두 사례는 guest PA `0x80041000`의 shifted 값도 확인한다. trace에서 fault PC와 fault 주소를 따로 대조했으며 `scripts/audit_profile_contracts.py`가 현재 해시·케이스·trap을 확인한다.

## CSR 쓰기와 SRET 직후 인터럽트

`scripts/run_guest_interrupt_priority.py`는 HS에서 지원하는 인터럽트 소스
일곱 개를 동시에 대기시켰다. 핸들러가 처리한 소스의 enable 비트만
지우자 `SEI → SSI → STI → VSEI → VSSI → VSTI → LCOFI` 순서로
전달됐다. VS로 위임한 세 소스와 HS의 SSI가 동시에 대기할 때는 HS가
먼저 처리했고, 이어서 게스트가 `SEI → SSI → STI`를 받았다. 각 트랩의
복귀 PC와 HS·VS의 실제 `scause`를 retire 기록과 대조했다.
[H 확장 인터럽트 규격](https://docs.riscv.org/reference/isa/priv/hypervisor)

`scripts/run_guest_timer_wrap.py`는 CLINT의 `mtime`을 두 값으로 설정해
`mtime + htimedelta`가 64비트 경계를 넘는 조건을 만든다. 경계 전에는
가상 시간이 큰 unsigned 값으로 비교되어 `hip.VSTIP`가 1이었고, 경계
후에는 작은 값으로 돌아오면서 0이 됐다. `hvip.VSTIP`만 설정한 경우와
타이머 비교가 계속 참인 상태에서 주입 비트만 지운 경우에도 pending 값을
확인했다. VS의 `time` 읽기에서 경계를 넘은 값이 관찰됐고, VS가 SIE를
설정하자 주입된 타이머가 다음 명령 전에 게스트 cause 5로 전달됐다.
[Sstc 규격](https://docs.riscv.org/reference/isa/v20250508/priv/sstc.html)

`run_counter_permission_matrix.py`의 `timer_read`와 `timer_write`는
M·HS·VS·U·VU에서 `stimecmp`와 `vstimecmp`를 각각 접근한다. M과 H의
STCE·TM 비트를 조합한 320개 접근에서 물리·가상 비교값을 구별했고, 합법
접근 82건과 cause 2 예외 208건, cause 22 예외 30건을 확인했다. 합법
쓰기는 이전 값과 새 값을 읽었고, 예외 핸들러는 명령의 EPC·tval과
원래 권한 상태를 확인했다. [Machine 1.13, mcounteren과 menvcfg](https://docs.riscv.org/reference/isa/v20260120/priv/machine.html) · [H 1.0, hcounteren과 henvcfg](https://docs.riscv.org/reference/isa/v20260120/priv/hypervisor.html)

HS의 `sie`와 `sip`는 `mideleg`에서 HS 인터럽트 비트만 선택한다.
이전 RTL에서는 HS가 `sie`에 VSEIE 위치의 비트를 쓰면 `hie.VSEIE=0`인
상태에서도 `hvip.VSEIP`가 HS로 전달됐다. 수정 후 동일한 ELF를 실행해
그 쓰기로는 인터럽트가 발생하지 않고, `hie`로 활성화했을 때 HS에서
cause 10을 받는 것을 확인했다. `hideleg`로 VS에 위임한 경우 게스트가
`scause`에서 cause 9를 읽었다. M의 `mie`와 `hie`, 그리고 `hideleg`에
따라 노출되는 `vsie` 별칭도 확인했다. 두 실행의 ELF와 trace는
`out/rva23/hypervisor_sie_isolation`에 있다.
재현 시 `scripts/run_hypervisor_sie_isolation.py --before`는 출력 디렉터리에
`sie` 쓰기만 수정 전 방식으로 되돌린 CSR 사본을 생성해 별도 모델을
빌드한다. 옵션 없이 실행하면 그 ELF를 현재 RTL에서 재생한다. 감사는
CSR 쓰기 한 곳에 해당하는 차이와 두 모델·ELF·trace의 해시를 확인한다.
[H 확장 인터럽트 CSR 규격](https://docs.riscv.org/reference/isa/priv/hypervisor)

Supervisor 1.13은 SIE, SIP, SSTATUS에 대한 명시적 쓰기나 SRET 직후 인터럽트 조건을 즉시 평가하도록 요구한다. HS와 VS 각각에서 SSTATUS.SIE, SIE.SSIE, SIP.SSIP를 마지막으로 설정하는 세 조합과, 대기 중인 인터럽트를 SRET으로 활성화하는 조합을 실행했다. 여덟 경우 모두 다음 명령이 retire되기 전에 인터럽트가 전달됐으며, SRET 사례의 SEPC는 SRET 다음 주소가 아니라 지정된 복귀 주소였다. 핸들러가 SEPC, SPP/SPIE/SIE, SCAUSE와 STVAL을 검사하고 동일 PC로 복귀했다. 이 실행은 소프트웨어 인터럽트를 사용한다. [Supervisor 1.13](https://docs.riscv.org/reference/isa/priv/supervisor.html) · [H 확장](https://docs.riscv.org/reference/isa/priv/hypervisor)

## MRET·SRET 복귀 후 스칼라와 벡터 접근

`run_xret_memory_contract.py`는 M에서 M·HS·U·VS·VU로의 MRET과
M·HS·VS에서의 SRET을 포함해 13개 경로를 실행했다. HS와 VS는 같은
가상 주소를 서로 다른 SRAM 페이지에 매핑했다. 복귀 직후 스칼라
load와 벡터 load가 각각 권한에 맞는 값을 읽었고, 이어진 M 모드
ECALL 핸들러가 `MPP`·`MPV`·`MPRV`와 `hstatus.SPV`를 확인했다.
M으로 돌아오는 대조군은 `MPRV=1`, `MPP=U`를 확인한 뒤 U 매핑을
읽었다. 동일 ELF의 Sail·RTL 실행 이벤트 746개가 일치했다.
[Machine 1.13 복귀 동작](https://docs.riscv.org/reference/isa/priv/machine.html) · [H 1.0](https://docs.riscv.org/reference/isa/priv/hypervisor)

## RVV 스칼라 이동의 재시작 경계

`run_vector_scalar_moves.py`는 LMUL=1·8에서 같은 레지스터 v3를 사용해
정수 스칼라 이동 80건과 FP 스칼라 이동 40건을 실행했다. `vl=0`과
`vstart`가 `vl`보다 작거나 같거나 큰 경우를 검사했다. 스칼라로 읽을
때는 0번 원소가 반환됐고, 벡터로 쓸 때는 0번 원소가 실행 범위에 있을
때만 바뀌었다. 나머지 비트는 tail-undisturbed 설정에 따라 보존됐다.
단정밀도 NaN boxing과 잘못 boxing된 입력의 canonical NaN, 실행 완료
후 `vstart=0`도 확인했다.

마스크가 설정된 네 이동 인코딩과 Zvfh가 필요한 반정밀도 FP 이동 두
가지는 cause 2를 발생시켰다. 핸들러가 EPC와 tval을 확인했고 `vstart`는
예외 전 값 1을 유지했다. 같은 ELF에서 Sail과 RTL의 실행 이벤트
2,915개를 대조했다. [V 1.0 스칼라 이동](https://docs.riscv.org/reference/isa/unpriv/v-st-ext#_integer_scalar_move_instructions)

## RVV 길이와 타입 설정

`run_vector_config_contract.py`는 전체 H/V SoC에서 레지스터 형식의
`vsetvl` 928건을 실행했다. `vtype` 하위 8비트의 모든 인코딩과 상위
56비트의 단일 비트 설정을 확인했다. 지원하는 22개 SEW/LMUL 조합에서는
네 가지 마스크·tail 정책과 함께 AVL 0, VLMAX 전후, 2×VLMAX 전후,
최대 64비트 unsigned AVL을 사용했다. 중간 AVL 범위에서는 RTL이
VLMAX를 반환하는 구현 정책을 적용한다.

설정 전환 13건은 세 명령 형식, `rd=x0` 및 `rs1=x0`의 조합,
정수 목적지와 입력 레지스터가 같은 경우를 다룬다. 같은 VLMAX로
SEW/LMUL을 바꾸면 `vl`이 유지됐고, RTL이 `vill`을 설정하는 예약
형식에서는 유효한 설정 명령으로 복구했다. 총 `vill` 결과 229건을
포함해 각 설정 직후 `vtype`·`vl`·`vstart`를 확인했다. 같은 ELF의
Sail·RTL 실행 이벤트 16,908개가 일치했다.
[V 1.0 설정 명령](https://docs.riscv.org/reference/isa/unpriv/v-st-ext#_configuration_setting_instructions_vsetvli_vsetivli_vsetvl)

## RVV 고정소수점 반올림과 포화 상태

`run_vector_fixed_point_contract.py`는 `vsmul.vx`의 SEW 8·16·32·64와
`vnclip.wi`의 SEW 8·16·32에서 네 가지 `vxrm` 모드를 실행했다.
독립 정수 계산으로 반올림과 포화 결과를 계산하고, 마스크·tail·복귀
인덱스로 제외된 원소와 이미 설정된 포화 플래그의 보존을 확인했다.
392개 사례에서 결과 원소 1,568개와 `vxsat`·`vcsr`·`vstart`를 검사했다.
같은 ELF의 Sail·RTL 실행 이벤트 14,288개가 일치했다.
[V 1.0 고정소수점 규격](https://docs.riscv.org/reference/isa/unpriv/v-st-ext)

## 스칼라와 벡터의 공유 SRAM 접근

`python scripts/audit_scalar_vector_order.py`는 아래 공유 메모리·재시작,
Svpbmt 별칭, PLIC 인터럽트, FENCE/CBO 및 분기 복구의 여섯 실행 보고서를 함께
재검사한다. 현재 모델 입력·실행 파일·ELF·드라이버·trace·로그의 해시를
확인하고, Sail 대조와 버스/retire 순서 검사를 다시 실행한다. 결과는
`out/rva23/scalar_vector_order_audit.json`에 기록되며 통합 요구사항 감사에도
포함된다. 완료 전 벡터 retire, 누락된 벡터 claim, 누락된 zero-stride IO
읽기, 누락된 concurrent debug 쓰기 및 누락된 speculative dispatch로 기록을 변형한 다섯 대조군을
거부한다. 이 대조군은 감사기의 검사력을 확인하며 RTL 변형 실행은 아니다.

현재 벡터 decode는 모든 벡터 명령을 serializing으로 표시한다.
ROB head의 벡터는 `lsu_memory_idle` 및 스칼라 피연산자 준비를 기다린다.
serial barrier가 retire될 때까지 뒤의 dispatch를 막으므로 벡터와 뒤따르는
스칼라 실행의 중첩을 허용하지 않는다. 이 근거는 해당 직렬화 구현의
지향성 검증이며, 스칼라·벡터 동시 실행이나 전체 RVWMO 증명을 뜻하지 않는다.

`python scripts/run_vector_branch_order.py`는 긴 스칼라 DIV 결과를 기다리는
분기 뒤의 잘못된 경로에 벡터 store, 정수 벡터 쓰기, 설정 변경,
FP→벡터 이동, 잘못된 주소의 벡터 load 및 벡터→스칼라 이동을 배치한다.
관찰용 전체 SoC 테스트벤치에서 여섯 벡터 모두 speculative dispatch된 후
flush됐으며, 벡터 실행 시작과 retire/trap은 발생하지 않았다.
올바른 경로는 메모리, v8의 두 워드, VL=2, vstart=0 및 스칼라 목적지의
보존을 확인한다. 같은 ELF를 Sail, 일반 H/V 모델 및 관찰용 모델에서
실행했고 두 RTL trace 각각이 Sail 이벤트 291개와 일치했다.
`--check`는 저장된 실행 근거를 재검사하며 누락된 dispatch witness를 거부한다.

`run_scalar_vector_memory.py`는 다른 64비트 뱅크 및 64바이트 라인
경계를 포함한 네 위치를 Bare와 Sv39에서 실행했다. Sv39에서는
스칼라와 벡터가 서로 다른 가상 주소로 같은 물리 SRAM에 접근했다.
벡터 load는 스칼라 초기화와 byte·halfword·word 쓰기 및 `AMOADD.D`의
결과를 읽었고, 스칼라 load는 벡터 store 직후의 두 64비트 값을
확인했다. 양쪽 인접 워드도 보존됐다. 벡터 load 24건, 벡터 store와
AMO가 각각 8건이었고, 동일 ELF의 Sail·RTL 이벤트 936개가 일치했다.

`run_indexed_memory_restart.py`는 같은 Sv39 페이지에서 스칼라 load와
벡터 unordered indexed load/store에 Svade A/D 예외를 발생시켰다.
S 모드 핸들러가 예외 PC·주소와 `vstart`를 읽고 두 번째 페이지를
다른 SRAM 페이지로 다시 매핑한 뒤 같은 PC로 복귀했다. 벡터 load의
앞선 원소와 벡터 store 후 핸들러가 수정한 앞선 메모리 값이 보존됐다.
핸들러에서는 뒤따르는 스칼라 store가 아직 반영되지 않았음을 확인했다.
두 번째 페이지를 매핑하지 않은 마스크 load/store에서는 첫 두 원소만
갱신됐다.

Ordered indexed store `vsoxei64.v`는 원소 0·1·3이 같은 워드를 쓰고
원소 2가 Svade D-bit 예외를 내도록 구성했다. 핸들러에서 같은 워드에
원소 1의 값 22가 보였고, 후속 스칼라 store의 위치는 여전히 0이었다.
매핑을 바꾼 뒤 `vstart=2`부터 복귀해 원소 2를 새 물리 페이지에 쓰고
원소 3의 값 99를 반복 주소에 썼다. 후속 스칼라 load와 ordered indexed
load `vloxei64.v`가 두 물리 페이지의 최종 값을 확인했다. 스칼라,
ordered 및 unordered indexed 시나리오를 합쳐 같은 PC 재시도 4건과
동일 ELF의 Sail·RTL 이벤트 524개를 대조했다.
[V 1.0의 정확한 예외와 벡터 메모리 접근](https://docs.riscv.org/reference/isa/unpriv/v-st-ext)

## 전체 벡터 레지스터 이동

`run_vector_whole_moves.py`는 `vmv1r.v`·`vmv2r.v`·`vmv4r.v`·`vmv8r.v`를
모두 `vl=0`에서 실행했다. SEW 8·16·32·64마다 `vstart`를 처음, 중간,
마지막 원소로 설정했다. 동일 ELF의 공통 48개 사례에서 Sail·RTL 실행
이벤트 50,198개가 일치했다.

RTL은 추가 19개 사례도 통과했다. `vstart=evl`인 15개는 목적지를
그대로 유지했고, `vill=1`인 4개는 전체 그룹을 복사했다. 모든 RTL
사례에서 목적지와 인접 영역을 합쳐 8,576바이트를 비교했다. Sail 0.16은
같은 추가 사례에서 cause 2를 냈다. `vstart=evl`은 구현이 해당 명령에서
생성할 수 없는 `vstart`를 거부할 수 있다는 규칙이 적용된다. `vill`의
경우 RVV 1.0은 whole-register move가 가능한 명령임을 명시한다.
[RVV 1.0 vstart와 vill](https://docs.riscv.org/reference/isa/extensions/vector/_attachments/riscv-v-spec.pdf#page=13) · [전체 레지스터 이동](https://docs.riscv.org/reference/isa/extensions/vector/_attachments/riscv-v-spec.pdf#page=88)

## 벡터 store 중 PLIC 인터럽트

`run_vector_irq_boundary.py`는 128바이트 벡터 store의 첫 바이트 요청이
수락된 직후 PLIC 소스 1을 올렸다. 코어는 벡터 store 실행 중 인터럽트를
감지했다. 나머지 바이트를 쓰고 벡터 명령이 retire된 다음 M 모드
외부 인터럽트에 진입했으며, 복귀 후 스칼라 store가 한 번 실행됐다.
핸들러가 `mepc`, `mtval=0`, `vstart=0` 및 SRAM의 128바이트를
확인했다. [V 1.0의 정확한 예외](https://docs.riscv.org/reference/isa/unpriv/v-st-ext)

같은 테스트의 다음 단계는 PLIC 소스 2·3·4를 올리고, 원소 0과 2만
활성화한 `vloxei32.v`로 같은 claim 레지스터를 두 번 읽었다. 읽을 때
pending 상태가 바뀌는 레지스터에서 우선순위 순으로 ID 3과 2가 각 원소에
들어갔으며, 마스크된 원소 1과 3은 초기값 15를 유지했다. 바로 뒤의
스칼라 claim 두 번은 4와 0을 읽었다. PLIC AXI에서 벡터 읽기 두 번이 모두
수락된 뒤 스칼라 읽기 두 번이 수락됐음을 확인했다.
[PLIC claim 동작](https://docs.riscv.org/reference/plic/plic-claims.html)

## Svnapot의 64 KiB 매핑

`run_svnapot_contract.py`는 S, VS, G 및 VS·G의 두 단계 모두에서
64 KiB NAPOT 매핑을 구성했다. 4 KiB 하위 페이지 16개 모두에서
load/store를 확인하고, 두 단계 매핑의 G-stage를 다른 SRAM 영역으로
바꾼 뒤 새 물리 주소에서 같은 검사를 반복했다. S·VS·G 각각에서
예약된 PPN 하위 니블 15개를 시험해 페이지 예외 총 90건을 확인했다.

S 모드에서는 NAPOT 하위 페이지 경계를 넘는 벡터 load와 첫 번째·
마지막 페이지의 명령 실행도 확인했다. 스칼라 메모리 접근 250건을
포함한 동일 ELF의 Sail·RTL 실행 이벤트 9,716개가 일치했다.
[Svnapot 1.0](https://docs.riscv.org/reference/isa/v20240411/priv/svnapot.html)

## Svpbmt 속성이 다른 주소 별칭

`run_svpbmt_alias_order.py`는 같은 물리 SRAM을 기본 PMA, NC, IO로
매핑했다. 스칼라에서 벡터로, 벡터에서 스칼라로 전환하는 12개 쓰기·
읽기 조합에서 값을 확인했다. NC↔IO 사이에는 `FENCE IORW,IORW`를
사용했고, 캐시 가능 여부가 바뀌는 경우에는 비캐시 주소 별칭에서
`CBO.FLUSH`를 실행하고 앞뒤에 fence를 뒀다.

캐시 가능 주소로 돌아오는 네 경우에서 라인 재충전을 확인했다.
네이티브 AXI 계측은 64바이트 라인 재충전 10건, 비캐시 읽기 24건,
PMA 속성의 벡터 원소 읽기 4건을 확인했다. 동일 ELF의 Sail·RTL
실행 이벤트 369개가 일치했다. 이 비교에는 PBMT=IO의 zero-stride
벡터 접근도 포함했다. `x0` 이외의 레지스터에 stride 값 0을 넣고
`vl=4`로 반복 주소를 읽었다. AXI에서 벡터 읽기 4회와 마스크
`0101`을 적용한 벡터 쓰기 2회를 확인했다. 네 load 원소의 데이터와
후속 스칼라 load가 읽은 store 결과도 검사했다.
[Svpbmt 1.0 별칭 순서](https://docs.riscv.org/reference/isa/v20240411/priv/svpbmt.html)
[RVV 1.0 strided 접근](https://docs.riscv.org/reference/isa/extensions/vector/_attachments/riscv-v-spec.pdf#page=33)

## 남아 있는 전체 감사 범위

이 검토로 기본 확장 RV64I/M/A/F/D/C/B/V와 Ss1p13/H의 모든 조항 검토가 끝난 것은 아니다. 명령의 legal/illegal encoding, vector configuration/state/restart, S/VS/HS 상태 전이와 PMA/ordering의 기존 지향성·ACT 근거를 세부 조항에 연결하는 작업은 `RVA23_IMPLEMENTATION_CHECKLIST.md`에서 계속 추적한다. 어떤 행도 전체 프로파일 인증 또는 합성 타이밍 sign-off로 사용하지 않는다.

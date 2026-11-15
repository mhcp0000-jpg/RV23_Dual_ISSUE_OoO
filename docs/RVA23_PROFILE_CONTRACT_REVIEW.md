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
| Sstvecd / Shvstvecd: Direct vector 주소 | CSR commit은 BASE 전체를 보존하고 MODE=0을 허용한다. trap 주소 생성은 Direct이면 BASE를 그대로 사용한다. | `run_profile_csr_geometry.py`: S/VS 각각 76개 canonical 정렬 주소. 기존 실제 S/VS trap/return ELF와 함께 확인한다. |
| Sscounterenw / Shcounterenw: enable 쓰기 | `HPM_COUNTERS`로 HPM state와 S/H enable mask를 함께 생성한다. production의 구현 HPM3..6 비트는 writable이고 나머지 HPM은 RAZ다. | 960개 counter permission 사례, walking enable와 all-ones readback, HPM event/overflow ELF. |
| Ssu64xl: UXL=64 | physical/virtual S status read 경로가 UXL=2를 제공한다. | S/VS status 각각 UXL 쓰기 0..3 후 readback. 구현은 UXL=64를 유지한다. |
| Svbare / Shvsatpa / Shgatpa: MODE 대응 | satp/vsatp는 동일하게 Bare/Sv39를 허용하고 unsupported MODE의 전체 쓰기를 무시한다. hgatp는 Bare/Sv39x4이며 root PPN은 16KiB 정렬이다. | CSR geometry와 실제 S/VS/G translation·retry ELF. run_sv39x4_root.py는 GPA[40:39] 네 조합의 HLV.D/HSV.D, 41비트 범위 마지막 doubleword, bit 41의 guest-page fault를 검사한다. |
| Svade: A/D 처리 | read-only walker는 A=0 또는 store의 D=0을 permission fault로 처리하며 PTE를 쓰지 않는다. VS PTE의 G-stage 번역은 load 권한으로 검사하고 예외는 원래 명령의 접근 종류로 보고한다. | MMU 테스트 103개에는 VS 및 최종 G leaf의 A/D 조합과 암시적 PTE read의 A=0이 포함된다. 원래 fetch/load/store별 cause와 최종 접근 GPA 및 PTE GPA를 대조했다. Native S-mode `rv64si/dirty` Sail 비교는 소프트웨어의 A/D 수정 및 재시도를 확인한다. [특권 규격](https://docs.riscv.org/reference/isa/priv/hypervisor) |
| Ssstateen: S/H CSR view | `rv_hypervisor_stateen`이 S/H 각각 4개 view를 decode한다. H의 SE/ENVCFG와 S의 optional-state RAZ를 제공하고 CSR file의 trap 경로에 연결된다. | CSR geometry의 8개 view read/write와 별도로 `run_guest_stateen.py`가 게이트 7개 조합에서 VS 읽기 42건을 실행했다. 각 `hstateen[n].SE`는 해당 `sstateen[n]`을, `hstateen0.ENVCFG`는 `senvcfg`를 제어했다. 차단된 32건의 cause 22, 명령 인코딩과 `stval`, SRET 복귀를 확인했다. [Ssstateen 규격](https://docs.riscv.org/reference/isa/priv/smstateen.html) |
| Sstvala / Shvstvala: VA·명령 trap 값 | trap controller는 ROB의 precise tval을 전달하고 S/VS bank는 trap commit 때 이를 기록한다. fetch queue는 뒤쪽 parcel의 fault 주소를 별도로 보존한다. | scalar/vector memory faults, 33개 breakpoint metadata, privilege instruction matrix, 새 split-fetch 12개 사례. 전체 trap-state 공간의 완전 탐색은 아니다. |
| Shtvala: faulting guest PA | H CSR bank는 guest-page fault에 전달된 guest address를 2비트 우측 이동해 htval에 기록한다. implicit VS-PTE read는 별도 metadata를 전달한다. | G-stage/guest-memory ELF, MPRV implicit/explicit 10개 사례. split-fetch의 두 G-stage 사례는 뒤쪽 parcel GPA와 shifted htval/mtval2를 확인한다. |
| Supm / Ssnpm: PMLEN=0/7 | S/H envcfg와 HUPMM은 PMM=00/10을 지원하고 unsupported 값은 이전 legal PMM을 유지한다. pointer-mask 결과가 scalar/FP/A/CBO/V 주소 경로에 연결된다. | Bare/Sv39 pointer-mask ELF, HUPMM/HLVX/MPRV guest 접근 및 vector/CMO 연결 근거. |
| Zkt / Zvkt: 데이터 독립 지연 | scalar 고정 pipeline과 vector element/state 진행 조건을 검토했다. arithmetic data가 완료 시점을 바꾸지 않는 경로와 mask/control 예외를 구분한다. | scalar 동일-text 16개와 vector 84,348 paired probe, operand-dependent early-exit 복사본 거부. 범위는 `TIMING_CONTRACT.md`에 명시한다. |
| Svpbmt / Svnapot: PTE 속성 | walker는 PBMT reserved/disabled 값을 거부하고 64KiB NAPOT leaf의 인코딩과 주소 합성을 검사한다. | MMU 테스트는 VS/G PBMT 3×3 조합과 양쪽 PBMTE, S 및 VS/G의 64 KiB 서브페이지를 확인한다. 비정렬 HLV.D 9개는 최종 유형을 실제 접근에 적용하며 수정 전 모델은 같은 ELF에서 실패한다. |

## 추가한 경계 사례

`scripts/run_zvbb_native.py`는 ACT4의 생성 벡터 시험에 별도 항목이 없는
Zvbb의 16개 형식을 실제 RV64 SoC에서 실행한다. 합법적인 SEW 8/16/32/64
조합에서 일반 실행, 마스크와 `vstart=1`을 함께 적용한 실행, `vl=0`을
포함해 183건을 확인했다. 목적지 레지스터에서 읽은 64비트 값 1,464개와
`vstart` 초기화를 검사했으며, 감사에서 명령 인코딩과 마스크 비트도
대조한다. [Zvbb 규격](https://docs.riscv.org/reference/isa/unpriv/vector-crypto.html)

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

`scripts/run_vector_mixed_eew_sail.py`는 같은 소스의 mixed-EEW 사례를
HTIF ELF 하나로 만들어 Sail과 RV64 H/V RTL에서 실행한다. PC, 명령 인코딩,
예외 원인과 스칼라 writeback을 포함한 208개 이벤트가 일치했다. 일곱 번의
예외에서 핸들러의 `mtval`과 복귀 직후 `vstart`를 확인했다. 거부된
indexed segment store의 목적지 메모리도 보존됐다.

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
281, retire 286, 읽기 요청 291을 기록했다. 통합 감사가 테스트벤치와
모델, ELF, 실제 로그 해시를 대조하고 이벤트 순서를 다시 검사한다.
이 테스트는 일반 SRAM의 단일 하트 실행을 다룬다.
[RV64I가 상속하는 FENCE 규격](https://docs.riscv.org/reference/isa/v20240411/unpriv/rv32.html)

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

## 남아 있는 전체 감사 범위

이 검토로 기본 확장 RV64I/M/A/F/D/C/B/V와 Ss1p13/H의 모든 조항 검토가 끝난 것은 아니다. 명령의 legal/illegal encoding, vector configuration/state/restart, S/VS/HS 상태 전이와 PMA/ordering의 기존 지향성·ACT 근거를 세부 조항에 연결하는 작업은 `RVA23_IMPLEMENTATION_CHECKLIST.md`에서 계속 추적한다. 어떤 행도 전체 프로파일 인증 또는 합성 타이밍 sign-off로 사용하지 않는다.

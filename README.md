# RV23 Dual-Issue OoO

기존 core_from_home RTL을 선별해 시작한 **공식 RVA23S64 전체 구현 프로젝트**다.
2026-10-29 사용자가 V·H·D·S모드·MMU를 포함한 전체 프로파일로 목표를 확정했다.
현재 default XLEN=64이며 구현 진행표와 남은 필수 기능은 [RVA23_TARGET](docs/RVA23_TARGET.md)에 기록한다.
전체 프로파일 구현/검증은 아직 완료되지 않았다.
[2026-11-16 검증 및 작업 정리](docs/REPOSITORY_STATUS.md)

I-cache 32 KiB + D-cache 32 KiB, 각각 64-bit 2-bank, 메인 AXI64,
공용 SRAM 1 MiB, CLINT/PLIC, native halt/AXI/trace debug 구조를 사용한다.
B/Zicond, S모드/Sstc, Sv39/Svade/PBMT/NAPOT/Svinval, 메인 버스 LR/SC·AMO,
Zawrs, Zcb/Zcmop/Zimop, Ssnpm 포인터 마스킹, 캐시 블록 관리·zero를
연결했다. D·Zfhmin·Zfa도 FP64 레지스터와 메모리 경로까지 통합했고, 실제 RV64 ELF의
5,261개 연산 사례와 FS/SD·Sv39 예외를 검증했다. 정수·FP 미정렬 접근은 ROB head의
하드웨어 처리기로 연결했고 bank/line/page 경계와 권한 오류를 검증했다.
V·Zvfhmin·Zvbb도 VLEN128/ELEN64 실행부와 벡터 메모리·CSR·ROB 경로에 연결했고,
실제 ELF에서 정수·FP·메모리·Sv39 예외와 재시작을 검증했다. 전체 RV64 코어에서
H/Sha의 M/HS/VS 진입, Sv39x4, HLV/HSV/HLVX와 가상 인터럽트를 실행했다.
같은 구성에서 dual issue·execute·retire와, 긴 나눗셈을 앞질러 실행한 독립 명령도
관찰했다. 프로파일 조항별 상태와 Zkt/Zvkt 검증 범위는
[구현 체크리스트](docs/RVA23_IMPLEMENTATION_CHECKLIST.md)에 있다. 이전 RV32 소스와 검증 기록은
`baselines/rv32_verified_20261029`에 보관했고 명시적 RV32 회귀 구성도 유지한다.

- 합성 top: `rv23_soc_top`, default XLEN=64, 가상주소 64 / 구현 물리주소 32 bit
- source list: `rtl/filelist.f` 또는 `sim/sources.f`, 프로젝트 루트에서 사용
- 구성/주소/boot/debug 계약: [ARCHITECTURE](docs/ARCHITECTURE.md)
- 현재 프로파일 요구와 구현 상태: [RVA23_TARGET](docs/RVA23_TARGET.md)
- 이전 RV32 범위 기록: [RV32_TARGET](docs/RV32_TARGET.md)
- 반입 출처/hash: [import_manifest](docs/import_manifest.json)
- 현재 파일/hash: [source_manifest](docs/source_manifest.json)
- 실행한 검사와 한계: [VALIDATION](docs/VALIDATION.md)
- 기존 TIM과 캐시의 cycle 병목 비교: [CACHE_CYCLE_ANALYSIS](docs/CACHE_CYCLE_ANALYSIS.md)

```powershell
git submodule update --init --recursive
python -m pip install -r requirements-dev.txt
python scripts/check_rtl.py
python scripts/run_checks.py
python scripts/run_all_rv32_checks.py
```

실행 도구는 기존 설치된 `C:/rv_toolchains`의 Verilator 5.050, w64devkit 2.9.1,
xPack RISC-V GCC 15.2를 사용한다. 빌드와 로그는 모두 이 폴더의 `out/`에 생성한다.
ACT4와 Linux/OpenSBI의 일부 Windows 스크립트는 `C:/rv_workspaces/rv23`을 사용한다.
다른 곳에 clone했다면 이 경로에 프로젝트를 두거나 Windows junction을 연결한다.
`--lint-only`, `--memory-only`, `--cache-only`, `--boot-only`로 필요한 범위만 실행할 수 있다.
실제 실행 상태와 범위는 `out/elaboration.json`, `out/verification.json`을 확인한다.
소스 코드나 테스트의 존재만으로 PASS라고 표시하지 않는다.

## Linux 콘솔

32 MiB RTL 시뮬레이션에서 성공한 [Linux 6.12 콘솔 발췌](docs/evidence/linux-boot-2026-11-16.txt)를
저장소에서 바로 볼 수 있다. 검증에 사용한 작업 폴더에서는 전체 로그를 확인할 수 있다.

```powershell
Get-Content .\out\linux_bringup\mixed_eew\firmware\rtl.log -Tail 30
```

데모의 `/init`은 `RV23 LINUX INIT PASS`를 출력한 뒤 전원을 끈다.
기본 1 MiB 구성은 OpenSBI에서 S 모드로 인계하고 DTB와 타이머를 확인하는 별도
검사를 사용한다. [부팅 검증 기록](docs/RVA23_REQUIREMENT_AUDIT.md)

재사용: frontend/backend·FPU·LSU·PMP/CSR, AXI crossbar/bridges, PLIC/CLINT, SRAM primitive,
ROM/HostIF. 새 구현: 32 KiB cache, dual-LSU arbiter, IF adapter, 1 MiB SRAM wrapper,
system bus/top. old TIM fabric/top/대형 out/기존 시험 결과는 실행 설계에 포함하지 않는다.

기존 회귀: `python scripts/run_regression.py --resume` (unit/block/backend + exact FP).
소프트웨어 회귀: `python scripts/run_programs.py --resume` (ELF AXI 적재/readback + cached SoC).
추가 검증과 최종 판정은 현재 [검증 문서](docs/VALIDATION.md)를 따른다.

전체 회귀는 `run_all_rv32_checks.py`로 실행한다. RTL을 수정했다면 먼저 변경 내용을
검토하고 `--update-manifest`로 새 소스 해시를 기록한다. 단위 회귀의 `--resume`은
입력 RTL/TB와 실행파일 해시가 모두 같은 PASS에만 적용한다.

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

## 검증 현황

| 검사 | 확인한 결과 |
| --- | --- |
| ACT4 | 체크인 ELF 663/663, 생성 벡터 ELF 2,083/2,083, H·Sv39x4·PMP 보강 ELF 40/40 통과 |
| 후속 ACT4 | upstream이 요구하는 Sail 0.16으로 RVA23 필터의 체크인 ELF 607/607 및 별도 H·Sv39x4·PMP ELF 40/40 통과 |
| 후속 ACT4 생성 벡터 | 2,301개 전체의 Sail 기대값·ELF 생성 감사 통과, RTL 회귀 진행 중 |
| 스칼라 참조 비교 | 동일 ELF의 Sail/RTL 실행 168개, 사용자 모드 ELF 152개의 retire 기록 61,754건 일치 |
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

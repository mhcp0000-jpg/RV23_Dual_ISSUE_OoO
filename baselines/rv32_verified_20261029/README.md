# rv23프로파일

기존 core_from_home RTL을 선별해 시작한 **RV32IMFC_Zicsr_Zifencei 타깃의 새 SoC 개발 폴더**.
현재는 RV32 구성 OoO 코어 + I-cache 32 KiB + D-cache 32 KiB + 공용 SRAM 1 MiB +
메인 AXI4 + CLINT/PLIC + native halt/AXI/trace debug 경계를 구현한 초기 통합본이다.
각 L1은 64-bit 2-bank이고 main AXI는 64 bit다. IF 128-bit hit와 서로 다른 bank의
두 LSU read hit는 1-cycle 응답/동시 수락을 검증한다. D-cache write hit는 SRAM
쓰기 수락 snoop의 byte strobe를 merge해 라인을 유지한다.
폴더/module의 rv23 이름은 유지하지만 현재 목표는 RV32다. 표준 JTAG debug, Linux boot와 성능/STA sign-off는 별도 범위다.

- 합성 top: `rv23_soc_top`, default XLEN=32 (물리주소 32 bit)
- source list: `rtl/filelist.f` 또는 `sim/sources.f`, 프로젝트 루트에서 사용
- 구성/주소/boot/debug 계약: [ARCHITECTURE](docs/ARCHITECTURE.md)
- 최종 프로파일 요구와 차이: [RV32_TARGET](docs/RV32_TARGET.md)
- 반입 출처/hash: [import_manifest](docs/import_manifest.json)
- 현재 파일/hash: [source_manifest](docs/source_manifest.json)
- 실행한 검사와 한계: [VALIDATION](docs/VALIDATION.md)
- 기존 TIM과 캐시의 cycle 병목 비교: [CACHE_CYCLE_ANALYSIS](docs/CACHE_CYCLE_ANALYSIS.md)

```powershell
python -m pip install -r requirements-dev.txt
python scripts/check_rtl.py
python scripts/run_checks.py
python scripts/run_all_rv32_checks.py
```

실행 도구는 기존 설치된 `C:/rv_toolchains`의 Verilator 5.050, w64devkit 2.9.1,
xPack RISC-V GCC 15.2를 사용한다. 빌드와 로그는 모두 이 폴더의 `out/`에 생성한다.
`--lint-only`, `--memory-only`, `--cache-only`, `--boot-only`로 필요한 범위만 실행할 수 있다.
실제 실행 상태와 범위는 `out/elaboration.json`, `out/verification.json`을 확인한다.
소스 코드나 테스트의 존재만으로 PASS라고 표시하지 않는다.

재사용: frontend/backend·FPU·LSU·PMP/CSR, AXI crossbar/bridges, PLIC/CLINT, SRAM primitive,
ROM/HostIF. 새 구현: 32 KiB cache, dual-LSU arbiter, IF adapter, 1 MiB SRAM wrapper,
system bus/top. old TIM fabric/top/대형 out/기존 시험 결과는 실행 설계에 포함하지 않는다.

기존 회귀: `python scripts/run_regression.py --resume` (unit/block/backend + exact FP).
소프트웨어 회귀: `python scripts/run_programs.py --resume` (ELF AXI 적재/readback + cached SoC).
추가 검증과 최종 판정은 현재 [검증 문서](docs/VALIDATION.md)를 따른다.

전체 회귀는 `run_all_rv32_checks.py`로 실행한다. RTL을 수정했다면 먼저 변경 내용을
검토하고 `--update-manifest`로 새 소스 해시를 기록한다. 단위 회귀의 `--resume`은
입력 RTL/TB와 실행파일 해시가 모두 같은 PASS에만 적용한다.

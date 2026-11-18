# Zcb 1.0 절별 검토

기준은 [Zc* 1.0의 Zcb 정의](https://docs.riscv.org/reference/isa/v20260120/unpriv/zc.html)다.
현재 RV64 H/V 구성에서 Zca와 관련 B/M 의존 확장이 활성인 경우를 다룬다.

| 명령·계약 | 구현 연결 | 실행 근거 |
|---|---|---|
| C.LBU / C.LHU / C.LH | `rv_c_expander`가 compact base/destination 및 byte/halfword offset을 일반 load로 확장한다. | 548개 load. unsigned byte/halfword와 signed halfword를 독립 정수/바이트 모델로 검사한다. |
| C.SB / C.SH | 같은 expander에서 compact source/base와 unsigned offset을 일반 store로 확장한다. commit 및 cache 경로는 일반 store와 공유한다. | 408개 store의 전 바이트를 후속 guard load로 관찰한다. 주변 바이트 보존도 검사한다. |
| C.ZEXT.B / C.SEXT.B / C.ZEXT.H / C.SEXT.H / C.ZEXT.W / C.NOT | expander가 ANDI·B 확장·word zero-extension·XORI 경로에 연결한다. | 각 형식의 prime destination 8개와 12개 입력 패턴, 총 576개. bit 7/15/31/63 및 비영 상위 비트를 포함한다. |
| C.MUL | expander가 M 곱셈 경로로 연결한다. | prime rd/rs2의 64개 조합과 선택 데이터 12개, 총 768개. rd=rs2 및 다른 source 보존, low-64 결과를 검사한다. |
| 압축 길이 및 상태 | frontend는 원본 16비트 instruction을 보존하며 PC 길이는 2바이트다. | 모든 probe에서 원본 encoding, source 값, 목적지/메모리 결과, 다음 PC+2 및 FCSR 보존을 검사한다. |
| 의존 확장 | Zcb는 Zca를 요구하며 일부 연산은 Zba/Zbb 또는 M/Zmmul을 요구한다. | 현재 목표 구성의 활성 의존 확장에서 실행했다. feature-disabled 구성의 전체 illegal 공간 검사를 대신하지 않는다. |

## 실행 결과와 재검사

`scripts/run_zcb_contract.py`는 9개 ELF에서 2,300개 probe를 실행했다.
고유 인코딩은 메모리 896개, unary 48개, MUL 64개로 RV64 Zcb 합법
인코딩 1,008개를 포함한다. encoding 완전성과 모든 입력 값의 완전성은 구분한다.
메모리 956개 중 base/data 중첩은 172개, halfword 비정렬 24개,
64바이트 라인 경계 12개, 4 KiB 물리 주소 경계 6개다.

배치별로 동일 ELF를 Sail과 전체 H/V RTL에서 실행해 이벤트 53,712개가
일치했다. 별도 정수 모델과 ELF의 file-backed 초기 바이트를 사용하는 메모리
모델을 적용했다. 메모리 모델에 넘기는 복사본의 target instruction만 동등한
일반 load/store로 의미 변환한다. 원본 Sail 비교, raw encoding, PC 길이 및
결과 데이터 비교는 변환하지 않는다. 결과/관찰 바이트 변조 대조군 20개를 거부했다.

```text
python scripts/run_zcb_contract.py --check
python scripts/audit_rva23_requirements.py --with-integration-evidence --linux-variant supm --require-linux-supm
```

`--check`는 현재 generator/helper, RTL/model, reference, ELF, assembly,
trace 및 로그 해시를 확인하고 검사를 다시 수행한다. 결과는
`out/rva23/zcb_contract/report.json`에 기록한다.

이 실행은 M-mode Bare SRAM의 선택 데이터 검사다. 물리 페이지 경계 통과가
주소 변환·PMP·PMA·MMIO·page-fault/retry 검증을 뜻하지 않는다. 이 항목들은
기존 memory/privileged 테스트와 함께 검토하며 모든 compressed encoding의
fault 조합, 모든 operand 값, interrupt/ordering 스케줄 및 timing 증명은 남는다.
Zcmp/Zcmt/Zcf 같은 다른 확장의 구현 근거로 사용하지 않는다. 전체 RVA23S64
규격 감사와 완료 판정은 계속 열려 있다.

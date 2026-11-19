# Host Bare memory-head fast path

기준 RTL은 `672f061`이다. `perf/vector-bare-fast` branch의 별도 worktree에서
개발해 이전 후보의 10회 측정과 source를 보존했다. `52e19c4`에서 주 개발
branch `perf/vector-cache-simd`에 통합했다. 측정과 Linux replay는 고정 worktree에서 계속 실행한다.

## 구현

기존 `rv23_translation_port`는 nonvirtual 요청에서 M privilege이거나
SATP.MODE=Bare이면 요청 주소를 물리 주소로 반환한다. 그럼에도 상위
memory head가 TRANSLATE/WAIT_TRANSLATE 두 상태를 거쳤다.

새 `FAST_BARE` 경로는 그 조건 또는 HAS_MMU=0에서 주소를 등록하고 바로
CHECK로 진행한다. 32비트를 넘는 물리 주소는 기존 access fault와 전체
tval을 반환한다. CHECK의 원소·그룹 PMP, PMA, MMIO/execute 및 idempotent
조건을 유지한다. Bus response와 register writeback 완료도 계속 기다린다.

비정렬 접근은 여전히 모든 바이트를 원래 순서로 preflight한다. 추가 바이트의
TRANSLATE에서는 직접 주소를 준비하고 CHECK로 간다. 이때 번역 포트에는
요청하지 않아 수신자가 없는 번역 응답이 남지 않게 한다. 가상 접근과
nonvirtual Sv39는 기존 번역 포트를 사용한다. Linux의 translated S-mode
메모리가 같은 비율로 빨라졌다고 해석하지 않는다.

새 translation cache나 permission reuse를 만들지 않는다. Single outstanding,
AXI64 및 기존 2/4/8-byte unit-load grouping은 유지한다. `FAST_BARE=0`으로
기존 제어 경로도 실행할 수 있다. 실제 STA/Fmax는 측정하지 않았다.

## 확인한 결과

- 직접 head의 FAST_BARE=0/1 비교: 각각 148 checks, 420 physical requests.
  주소·write·size·data·strobe·device 속성의 **전체 요청 순서와 payload가 같다**.
  독립 값/fault 검사를 모두 통과했고 test stream은 **3,511→2,821 cycles**다.
- Mixed Bare/Sv39 vector memory owner 15,957 packets / 4,654 physical bytes 통과.
  Misaligned Bare 이후 translated 요청, PMP/row/vstart/tail/FF/segment와 fault를 포함한다.
- Native M/HS/VS H/V 및 VS Sv39 shared D-cache 확인 통과.
- Word-load IRQ 12개 통과: EEW8/16/32 × 전체/2원소 VL × warm/cold.
  모든 active 결과와 마지막 RF write→retire→trap, younger scalar store 순서를 검사했다.
- 기존 vector-store IRQ와 PLIC claim 순서 검사 통과. Pending 당시 1바이트가
  수락됐고 vector store→interrupt→scalar store→vector claim 순서였다.

같은 진단 ELF의 128회 warmed probe는 아래와 같다. Frontend/call/CSR
비용을 포함하며 독립 FU latency나 CoreMark 전체 개선율은 아니다.

| 경로 | 이전 cycles | 변경 후 cycles | 감소율 |
|---|---:|---:|---:|
| VLE64 / VLUXEI64 | 3,029 | 2,517 | 16.90% |
| Full-width VLE8/16/32 | 3,046 | 2,542 | 16.55% |
| VLE8, VL2 | 2,133 | 1,912 | 10.36% |
| VLE16, VL2 | 2,164 | 1,877 | 13.26% |
| VLE16, VL2, base offset 4 | 2,220 | 1,933 | 12.93% |
| VADD | 1,295 | 1,295 | 0.00% |

같은 CoreMark 2회 ELF는 **1,814,469→1,761,562 cycles**, **2.9158% 감소**다.
명령 수 552,447과 CRC가 같고 IPC는 **0.304468→0.313612**다.
ELF는 재컴파일하지 않았다.

같은 10회 ELF도 **8,784,522 cycles**, 명령 수 **2,762,088**, IPC
**0.314427**, CoreMark/MHz 추정 **1.138366**으로 완료했다. CRC가 같다.
직접 실행 보고서의 기준 `009b013`은 9,054,053 cycles로, grouping과 Bare
단계의 합산 감소는 **2.9769%**다. 별도로 완료한 `672f061`의 9,049,013
cycles와 비교하면 **Bare 단계만 2.9229% 감소**다.

두 완료 실행의 독립 비교는 `compare_completed_vector_coremark.py`에서
같은 ELF/params/CRC/instruction count, 실제 로그 packet과 executable hash,
변경된 RTL이 memory head 한 파일뿐임을 확인했다. 새 실행으로 표시하지 않는다.
[소스와 회귀·진단 근거](evidence/vector_bare_fastpath.json).
전체 RVA23S64 적합성이나 모든 경합의 증명은 아니다.

```powershell
python scripts/run_hypervisor_memory_head_checks.py
python scripts/run_vector_memory_engine_checks.py
python scripts/run_vector_word_irq.py --output-dir out/rva23/vector_word_irq_bare
python scripts/run_vector_irq_boundary.py
python scripts/profile_vector_latency.py --baseline-dir out/performance/vector_bare_before --output-dir out/performance/vector_bare_latency --include-small-loads --include-short-vl --expect-improved vle64 vle32 vluxei64 vle8 vle16 vle8vl2 vle16vl2 vle16vl2off4
python scripts/compare_vector_overlap_performance.py --coremark-iterations 2 --baseline-dir out/performance/vector_bare_before --output-dir out/performance/vector_bare --before-commit 672f061 --expected-changes rtl/backend/rv23_hypervisor_memory_head.sv
```

비교에는 보존한 이전 모델과 동일 ELF가 필요하다.

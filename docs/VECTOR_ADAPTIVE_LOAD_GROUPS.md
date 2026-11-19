# Adaptive vector unit-load groups

`001ce80`의 8-byte 전용 후보에서 2/4/8-byte 그룹을 선택하도록 확장했다.
현재 작업 branch는 `perf/vector-memory-coalesce`이며 주 개발 branch에는
아직 통합하지 않았다. [첫 후보 기록](VECTOR_WORD_LOAD_COALESCING.md)을 보존한다.

## 구현과 선택 근거

첫 후보의 연속 load 진단은 개선됐지만 같은 CoreMark 2회 ELF의 사이클은
1,815,477로 같았다. 해당 ELF의 `copy_info`에는 `VL=2, e16, mf4` load가
있다. 4바이트만 읽는 이 명령은 8바이트 전체를 요구하는 첫 후보의 적용
대상이 아니었다. 새 선택은 특정 PC를 검사하지 않고 VL, 주소, EEW와
destination row만 사용한다.

Engine은 남은 active 원소와 한 128-bit RF row 안에 들어가는 가장 큰
정렬된 2/4/8-byte 그룹을 고른다. 그룹은 반드시 원소보다 커야 한다.
Nonzero vstart에서 시작하거나 주소가 8바이트 워드 중간이어도 작은 그룹을
선택할 수 있다. Mask/FF/whole/segment/indexed/strided load와 store는
기존 원소별 경로를 유지한다.

Memory head는 그룹 크기를 요청 시 register에 캡처하고, translation 후
그 크기의 **전체 PMP read 권한**과 **normal PBMT SRAM**을 확인한다.
묶을 수 없으면 원래 원소 크기로 처리한다. 응답에는 실제 그룹 크기도
등록해 전달한다. Engine은 그 크기만큼 index를 진행하고 해당 byte mask만
registered packed RF write에 반영한다. 응답의 그룹 밖 bit는 0으로 만든다.
Vstart 앞이나 VL 뒤를 추가로 읽거나 덮지 않는다.

단일 outstanding 요청과 AXI64는 유지한다. 이 변경은 128-bit vector
memory issue, burst/MO 또는 vector-vector OoO의 구현이 아니다.

## 완료된 진단과 회귀

같은 새 진단 ELF를 보존한 첫 후보 binary와 새 모델에 실행했다.
CoreMark ELF는 재컴파일하지 않았다. 아래 수치는 frontend/call/CSR 비용을
포함한 128회 warmed probe이며 실제 Fmax/STA는 측정하지 않았다.

| 경로 | 이전 cycles | 변경 후 cycles | 감소율 |
|---|---:|---:|---:|
| VLE8, VL2 | 3,029 | 2,133 | 29.58% |
| VLE16, VL2 | 3,046 | 2,164 | 28.96% |
| VLE16, VL2, base offset 4 | 3,102 | 2,220 | 28.43% |
| 기존 full-width VLE8/16/32 | 3,046 | 3,046 | 0.00% |
| VLE64 / indexed VLE64 | 3,029 | 3,029 | 0.00% |
| VADD | 1,295 | 1,295 | 0.00% |

- Memory owner: 15,957 packets / 4,654 physical bytes 통과. 118개 그룹
  사례의 실제 batching 횟수와 모든 원소 값을 독립 byte oracle로 확인했다.
  짧은 VL, fractional LMUL~LMUL8, offset, row 경계, vstart/tail, EEW≠SEW,
  PMP fallback과 precise fault를 포함한다.
  큰 묶음의 PMP 거부 후 작은 묶음을 수락하다 다음 원소에서 fault 나는
  경우에도 vstart=4와 앞선 네 원소의 보존을 확인했다.
- Bare memory head: 148 checks 통과. 2/4/8-byte PMP 허용·거부와 MMIO
  크기 보존, backpressure의 stable response metadata를 확인했다.
- Native H/V 및 VS Sv39 공유 D-cache 확인 통과. Guest VLE32 네 원소가
  read 두 건으로, VSE32는 기존 write 네 건으로 실행됐다.
- Native PLIC IRQ 12개: EEW8/16/32 × 전체 128바이트/2원소 × warm/cold.
  모든 active 결과를 handler에서 대조했다. 마지막 RF write → retire → trap
  순서와 younger scalar store의 외부 반영 순서를 확인했다.
- 같은 CoreMark 2회 ELF는 **1,815,477→1,814,469 cycles**, **0.0555% 감소**다.
  명령 수 552,447과 CRC가 같고 IPC는 **0.304299→0.304468**이다.
  연속 load 진단의 개선을 전체 benchmark 개선율로 사용하지 않는다.
- 같은 10회 ELF는 **9,054,053→9,049,013 cycles**, **0.0557% 감소**다.
  명령 수 2,762,088과 CRC가 같고 IPC는 **0.305236**이다.
  10회의 기준은 `009b013`이며 2회/진단의 기준은 8-byte 전용 `001ce80`이다.

[소스·측정·회귀의 해시 근거](evidence/vector_adaptive_load_groups.json).
전체 RVA23S64 적합성이나 모든 메모리/인터럽트 경합의 증명은 아니다.

```powershell
python scripts/run_vector_word_irq.py --output-dir out/rva23/vector_word_irq_adaptive
python scripts/profile_vector_latency.py --baseline-dir out/performance/vector_word64_before --output-dir out/performance/vector_adaptive_latency --include-small-loads --include-short-vl --expect-improved vle8vl2 vle16vl2 vle16vl2off4
python scripts/compare_vector_overlap_performance.py --coremark-iterations 2 --baseline-dir out/performance/vector_word64_before --output-dir out/performance/vector_adaptive --before-commit 001ce80 --expected-changes rtl/backend/rv_vector_engine.sv rtl/backend/rv23_hypervisor_memory_head.sv
```

비교에는 로컬에 보존한 변경 전 모델과 같은 고정 ELF가 필요하다.

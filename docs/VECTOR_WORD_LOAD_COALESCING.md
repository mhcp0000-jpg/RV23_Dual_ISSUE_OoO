# Vector unit-load word coalescing candidate

이 단계는 `009b013` RTL을 기준으로 개발 중인 후속 성능 변경이다.
주 작업 폴더의 10회 측정을 보존하기 위해 별도 worktree
`C:/rv_workspaces/rv23-vector-memory`, branch `perf/vector-memory-coalesce`에서
작업한다. 아직 주 개발 branch에 통합하지 않았다.

## 동작

기존 경로는 EEW8/16/32의 연속된 원소도 각각 translation/permission 및
physical request/response 절차를 수행한다. 후보 경로는 같은 64-bit word의
완전한 8/4/2개 원소를 한 번의 64-bit 공유 D-cache 읽기로 처리한다.
반환된 8바이트는 기존 registered packed RF write 경로에 넣는다.

Vector engine은 unmasked unit-stride load, 단일 field, EEW<64, 정렬된
원소 그룹, VL 안에 완전히 들어가는 그룹만 후보로 보낸다. Mask/whole/FF,
indexed/strided/segmented load와 store는 기존 경로를 유지한다. Vstart 앞과
VL 뒤의 원소를 읽거나 덮지 않는다. Encoded EEW가 arithmetic SEW와 다른
경우에도 packed RF write의 폭은 encoded EEW를 따른다.

Memory head는 translation 후 **정상 PBMT의 SRAM**과 **8바이트 전체 PMP
read 권한**을 별도로 확인한다. 원소 접근은 허용돼도 8바이트 전체 접근이
한 PMP 영역에서 허용되지 않으면 원래 크기로 실행한다. 더 넓은 접근의
거부를 새 architectural fault로 바꾸지 않는다. MMIO와 ROM은 묶지 않는다.
`COALESCE_READ` parameter는 기본 0이며 vector owner만 켠다.

이 변경은 새로운 private cache를 만들지 않는다. 기존 공유 D-cache의
요청 수를 줄이는 것으로, 128-bit vector memory issue나 여러 outstanding
요청, AXI burst/MO 또는 통합 Permutation/Load/Store unit의 구현은 아니다.
물리 타이밍/Fmax는 아직 측정하지 않았다.

## 현재 확인

- Memory owner: 10,333 packets / 3,580 physical bytes 통과. 22개 coalescing
  사례에서 실제 묶인 요청 수를 확인하고 모든 원소를 독립 byte oracle과
  비교했다. Fractional LMUL~LMUL8, row/group 경계, vstart와 tail, EEW≠SEW,
  인접 NA4 PMP 영역 fallback 및 두 번째 원소의 precise fault를 포함한다.
- Bare memory head: 145 checks 통과. 실제 64-bit SRAM read와 MMIO의
  원래 접근 크기 유지, 비정렬 word fallback, split PMP 영역을 확인했다.
- Native M/HS/VS H/V 통합 ELF 통과.
- VS Sv39 guest의 4개 VLE32 원소가 공유 D-cache의 **64-bit read 2건**으로
  처리되는 것을 관측했다. VSE32는 기존대로 write 4건이며 cache hit도 확인했다.
- 실제 코어의 같은 진단 ELF 비교에서 아래 연속 load 개선을 확인했다.
  모든 128-bit 결과를 vector store → scalar load로 대조했다.
- 같은 CoreMark 2회 ELF 측정은 진행 중이다. 전체 benchmark 개선율은
  완료된 결과로만 추가한다.

| 128회 warmed probe | 이전 cycles | 후보 cycles | 감소율 |
|---|---:|---:|---:|
| VLE8 | 15,573 | 3,046 | 80.44% |
| VLE16 | 8,405 | 3,046 | 63.76% |
| VLE32 | 4,821 | 3,046 | 36.82% |
| VLE64 | 3,029 | 3,029 | 0.00% |
| VLUXEI64 | 3,029 | 3,029 | 0.00% |
| VADD | 1,295 | 1,295 | 0.00% |

연속 load 사례와 전체 결과 검사를 추가한 새 **진단 ELF**이며, 두 모델에는
그 동일 ELF를 실행했다. 이전 진단과 code layout이 다르므로 각 진단의
before/after 쌍 안에서 비교한다. 보존된 CoreMark ELF는 재컴파일하지 않았다.
수치는 frontend/call/CSR 비용을 포함하며 실제 Fmax나 독립 유닛 latency가 아니다.
[소스·진단·회귀 해시 근거](evidence/vector_word_load_coalescing.json)

```powershell
python scripts/run_vector_memory_engine_checks.py
python scripts/run_hypervisor_memory_head_checks.py
python scripts/run_hypervisor_integration.py
python scripts/run_vector_coalesce_guest_cache.py
python scripts/profile_vector_latency.py --baseline-dir out/performance/vector_coalesce_before --output-dir out/performance/vector_coalesce_latency --include-small-loads --expect-improved vle8 vle16 vle32
python scripts/compare_vector_overlap_performance.py --coremark-iterations 2 --baseline-dir out/performance/vector_coalesce_before --output-dir out/performance/vector_coalesce --before-commit 009b013 --expected-changes rtl/backend/rv_vector_engine.sv rtl/backend/rv23_hypervisor_memory_head.sv
```

성능 비교에는 로컬에 보존한 이전 실행 모델과 고정 ELF가 필요하다.

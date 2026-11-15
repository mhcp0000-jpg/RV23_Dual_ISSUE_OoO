"""Publish documentation/snapshot only from a fresh successful release audit."""
import json,re
from datetime import datetime
from sim_runner import ROOT,sha,dump
def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
audit=read('out/rv32_release_audit.json');assert audit['passed'] and len(audit['gates'])==6
validation_date=datetime.now().astimezone().isoformat(timespec='seconds')
for p,d in audit['source_sha256'].items():assert sha(ROOT/p)==d,p
perf=read('out/performance/banked_after/report.json');assert perf['passed']
for p,d in perf['after_model_inputs'].items():assert sha(ROOT/p)==d,p
cases={c['iterations']:c for c in perf['cases']};two=cases[2];ten=cases[10]
wt=read('out/performance/write_path/report.json');assert wt['passed']
assert wt['current_report_sha256']==sha(ROOT/'out/performance/banked_after/report.json')
assert audit['coremark']['cycles']==two['after']['cycles']
base=read('out/verification.json')
summary={x['top']:x['summary'] for x in base['results']}
checks=lambda name:int(re.search(r'checks=(\d+)',summary[name])[1])
old=two['before'];new=two['after'];control=two['control_stream']
assert control['passed']
for side in ['before','after']:assert sha(ROOT/control[side+'_trace'])==control[side+'_trace_sha256']

def table():
    lines=['| Iter | 수정 전 cycles | 수정 후 cycles | 수정 전 IPC | 수정 후 IPC | cycle 기준 배속 |',
           '|---|---:|---:|---:|---:|---:|']
    for n in [2,10]:
        c=cases[n];b=c['before'];a=c['after']
        lines.append(f"| {n} | {b['cycles']:,} | {a['cycles']:,} | {b['ipc']:.6f} | {a['ipc']:.6f} | {c['speedup']:.3f}× |")
    return '\n'.join(lines)

wt_lines=['| Iter | 직전 banked cycles | 현재 cycles | 직전 IPC | 현재 IPC | cycle 감소 |',
          '|---|---:|---:|---:|---:|---:|']
for c in wt['cases']:
    wt_lines.append(f"| {c['iterations']} | {c['before_cycles']:,} | {c['after_cycles']:,} | "
                    f"{c['before_ipc']:.6f} | {c['after_ipc']:.6f} | {c['cycle_reduction_percent']:.2f}% |")
for label in ['wt_before','after']:
    model=read(f'out/performance/memory_latency_{label}/report.json');assert model['passed']
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
    assert sha(ROOT/model['run']['log'])==model['run']['log_sha256']
def latency(label,port,address,writing):
    log=(ROOT/f'out/performance/memory_latency_{label}/simulation.log').read_text()
    return int(re.search(fr'MEM_LAT port={port} addr={address} write={writing} cycles=(\d+)',log)[1])
store_before,store_after=[latency(label,0,'80000600',1) for label in ['wt_before','after']]
mmio_before,mmio_after=[latency(label,1,'02000000',0) for label in ['wt_before','after']]
assert store_after<store_before and mmio_after<mmio_before
write_section=f'''## Write-through 경로 추가 수정

두-bank 적용 직후의 IPC와 별도로, 이번에는 cache engine의 요청 저장→SEND 대기와
bridge의 registered 응답→cache 응답 저장 대기를 줄였다. 빈 engine은 수락 cycle에
요청을 내보내며, downstream이 막히면 같은 payload를 저장해 유지한다. write/uncached
read는 실제 bridge 응답을 바로 전달하고 CPU가 받지 않으면 포트별 holding slot에
저장한다. refill 완료는 기존 registered 경로를 유지한다. store 완료는 bus 응답 뒤다.

동일한 시스템 probe의 SRAM store는 **{store_before} → {store_after} cycles**,
CLINT read는 **{mmio_before} → {mmio_after} cycles**다. I/D hit는 여전히 1 cycle이다.
아래는 직전 banked 구현과 동일 ELF를 비교한 추가 개선분이다.

{chr(10).join(wt_lines)}

직전 RTL/native binary/ELF/log는 `out/performance/wt_before/`에 별도로 보존했다.
`out/performance/write_path/report.json`은 그 결과와 현재 결과의 hash를 묶는다.
요청 수락 edge, stall 중 ID/주소/크기/privilege/ROB seq/data/strobe 보존, 버스 응답 전
완료 금지, ready CPU의 단일 완료, held response, 다른 LSU로의 owner 전환을 검사했다.
보존한 이전 RTL은 새 acceptance-edge 검사에서 실패하는 것도 확인했다.

'''

historical_section=''
historical_path='out/performance/tim_reference_elf/report.json'
if (ROOT/historical_path).exists():
    h=read(historical_path);assert h['passed']
    for p,d in h['model_inputs'].items():assert sha(ROOT/p)==d,p
    assert sha(ROOT/h['binary'])==h['binary_sha256']
    assert sha(ROOT/h['elf'])==h['elf_sha256']
    assert sha(ROOT/h['run']['log'])==h['run']['log_sha256']
    assert sha(ROOT/h['historical_report'])==h['historical_report_sha256']
    b=h['historical_tim'];a=h['current_cache'];assert a['instructions']==b['instructions']
    historical_section=f'''## 과거 TIM과 같은 ELF로 비교한 정정 결과

기존 CoreMark runner는 `rv32imc/ilp32`, function/data sections 및 linker GC를 사용했다.
새 회귀 runner에는 `rv32imfc/ilp32f`, `--no-relax` 공통 옵션을 적용했다. source/startup/
linker script가 같아도 실행 코드와 배치가 달라졌다. 캐시로 바꾼다는 이유로 ELF를
바꿀 필요는 없었으며, 과거 TIM 대비 비교 조건을 통제하지 못한 것이다.

과거 IPC 1.316246의 release 기록과 SHA-256이 같은 ELF를 찾아 재컴파일 없이
현재 cached SoC에서 실행했다. ELF SHA-256은 `{h['elf_sha256']}`이다.

| 구성 | cycles | timed instructions | IPC |
|---|---:|---:|---:|
| 과거 TIM 기록 | {b['cycles']:,} | {b['instructions']:,} | {b['ipc']:.6f} |
| 현재 cache, 위와 동일 ELF | {a['cycles']:,} | {a['instructions']:,} | {a['ipc']:.6f} |

CRC/exit도 통과했다. 이 표의 TIM 값은 보존된 과거 실행 기록이며 TIM을 새로
실행한 결과는 아니다. 동일 ELF로 맞췄지만 RTL 구성 차이의 원인별 cycle 분해를
완료한 것은 아니다. 위의 2/10회 cache A/B 표는 각 행 내부에서 같은 ELF를 사용한
유효한 비교이며, 그 IPC를 과거 TIM과 직접 비교하면 안 된다.
고정 ELF/과거 release 사본/현재 native log와 입력 hash는
`out/performance/tim_reference_elf/report.json`에 보존했다. 이후 TIM 대비 성능
판단에는 이 보존 ELF를 사용하며 재빌드한 파일로 조용히 교체하지 않는다.

'''

analysis=f'''# Cache cycle 분석과 수정 — 검증 갱신 {validation_date}

기존 코어의 연산 블록 대부분을 재사용했지만, 처음 통합할 때 메모리 경로의 처리량을
보존하지 못했다. main AXI는 원본도 현재도 64 bit다. 기존 TIM 내부 128-bit 병렬 읽기를
64-bit 순차 읽기로 대체한 것이므로, main bus 폭을 64 bit로 둔 것 자체가 하락 원인은 아니다.

## 실제로 늦어진 경로

| 항목 | 직렬 캐시 구현 | 현재 구현 |
|---|---|---|
| 128-bit instruction hit | 64-bit 두 번을 순서대로 처리, **9 cycles** | 64-bit 두 bank 동시 읽기, **1 cycle** |
| 64-bit data hit | arbiter + LOOKUP/CHECK/RESP, **4 cycles** | 직접 bank 동기 읽기, **1 cycle** |
| 서로 다른 bank의 두 read | 첫 응답이 끝날 때까지 다른 요청 수락 지연 | 같은 cycle 수락/응답 |
| 같은 bank의 두 read | 전체 transaction 직렬화 | read port만 한 cycle씩 round-robin |
| write hit | 해당 line을 버리고 이후 load가 refill | 실제 SRAM 쓰기 수락의 data/strobe를 resident word에 merge |
| 진행 중인 write와 다른 word | 같은 64B line 전체를 응답까지 차단 | 같은 8B word만 차단 |

`rv23_cache`는 512개의 shared tag/valid와 bank당 2,048 × 64-bit data를 가진다.
두 bank 합계가 32 KiB이며 I/D에 각각 하나씩 있다. bank bit는 address[3]이고,
정렬된 16B fetch는 항상 두 bank를 함께 읽는다. 두 LSU는 bank가 다르면 함께 처리한다.
bank당 1R1W이며, main SRAM 1 MiB로 향하는 외부 경로는 AXI64 그대로다. TIM 우회 경로를
추가한 것이 아니다. 각 캐시의 miss/write-through engine은 하나이며 다른 resident
word의 hit는 진행할 수 있다. store 성공 응답은 여전히 외부 버스 응답을 기다린다.

latency 단위는 수락 edge에서 첫 registered response까지의 clock 수다. canonical
memory TB는 1-cycle hit, 128-bit 연속 fetch, bank 충돌·응답 backpressure·쓰기 중 다른
word 진행을 assert한다. `profile_memory_paths.py --label before/after`의 독립 로그도 남겼다.

## 같은 ELF로 비교

{table()}

각 행은 동일 ELF 바이트를 보존한 수정 전/후 실행파일에 넣어 비교했다. 2회는
{two['after']['instructions']:,}명령, 10회는 {ten['after']['instructions']:,}명령으로 전후가 같고
seed/list/matrix/state CRC도 일치한다. 두 회수 모두 reset/cold start에서 시작한다.
별도로 warm-only 창을 분리한 측정은 아니며 10회까지의 반복 추세를 확인한 것이다.

전체 ELF 적재 후 계측에서 D-cache miss는 2회 {old['whole_program_cache']['d_miss']:,} →
{new['whole_program_cache']['d_miss']:,}, 10회 {ten['before']['whole_program_cache']['d_miss']:,} →
{ten['after']['whole_program_cache']['d_miss']:,}로 줄었다. 이 범위는 CSR timed 창보다 넓다.

## 심한 cycle 공백의 위치

`start_time` 진입부터 `stop_time` 진입까지 retire cycle group을 비교했다.
CSR 측정과 bookend가 다르므로 위 timed cycles와 구분한다.

| 지표 | 수정 전 | 수정 후 |
|---|---:|---:|
| 창의 cycle 수 | {old['retire_gaps']['cycles']:,} | {new['retire_gaps']['cycles']:,} |
| commit 없는 cycle 수 | {old['retire_gaps']['no_commit_cycles']:,} | {new['retire_gaps']['no_commit_cycles']:,} |
| 두 명령 commit cycle 수 | {old['retire_gaps']['dual_commit_cycles']:,} | {new['retire_gaps']['dual_commit_cycles']:,} |

수정 전 가장 큰 공백 집계는 `core_bench_list+0x42`, PC `0x800007d4`의
`lw a4,0(s0)` 앞이다. 이어지는 `sw a3,0(s0)`와 다음 노드 추적이 반복된다.
쓰기마다 cache line을 버리던 동작은 이 load/store 반복에서 특히 불리했다.
PC별 공백은 **다음 retire 묶음의 첫 PC에 배정한 간접 지표**이며, 그 명령 하나의
실행 지연이나 특정 원인의 stall cycle이라고 단정하지 않는다.

같은 창의 **{control['instructions']:,}개 명령**은 retire 순서·PC·opcode·목적지·trap·CSR
metadata가 전후 동일했다. `mcycle`에서 파생되는 operand 값은 비교에서 제외했다.
이는 전체 ISA/데이터 동등성 증명이 아니다.

## 동작과 보존 조건 검증

- 시스템 TB: {checks('rv23_memory_tb'):,} checks. 연속 128-bit fetch, dual bank, same-bank
  중재, 같은 line의 다른 word 진행, resident byte snoop, 실제 SRAM/PLIC/CLINT/debug.
- cache TB: {checks('rv23_cache_fault_tb'):,} checks. 512 lines × 8 words = 4,096 words의
  전체 32 KiB hit, 오류/부분 refill, final-beat invalidate, snoop/refill bank-write 충돌.
- 마지막 I-refill의 FENCE.I, code write와 refill, stalled 128-bit 응답의 안정성.
- 넓은 line lock의 이전 RTL은 새 progress 검사에서 실제 실패한다.
- 기존 58 block/backend, 22 RV32 ELF, 3 seeded memory scoreboard와 최종 6-gate audit.

{write_section}{historical_section}## 남은 성능 차이

이전 TIM의 IPC 1.316246은 별도 메모리 경로의 기록이다. cache A/B 표의 ELF와
달랐으며, 위 정정 표에 과거와 같은 ELF의 현재 측정을 분리했다. write-through 전송/응답은 main AXI에서 직렬 처리하며,
refill도 여전히 8개의 single-beat 전송이다. cache hit bandwidth와 외부 쓰기 처리량을
구분해야 한다. `PATH_PERF`의 engine busy cycle은 계산과 겹칠 수 있으므로 전부를
추가 stall로 합산하지 않는다. write combining/burst/write-back은 별도 설계·검증 항목이다.
새 주파수/STA 결과는 없으며 이 문서의 배속은 동일 clock의 cycle 수 비교다.

## 증거와 재현

`out/performance/banked_before/`에 직렬 구현 RTL/TB/native binary/2회·10회 ELF·로그를
보존했다. `out/performance/banked_after/report.json`은 전후 binary/source/ELF/log와
2회 retire CSV hash를 묶는다. `banked_stage1/`은 두-bank 적용 후 word-lock 보정 전의
중간 결과다. 이 중간 수치를 현재 결과로 취급하지 않는다.

```powershell
python scripts/run_all_rv32_checks.py
python scripts/profile_memory_paths.py --label after
python scripts/save_verification_snapshot.py
```

전체 runner는 입력/실행파일/hash가 같은 결과만 재사용한다. 기준 native binary/ELF
사본은 이 프로젝트의 보존 산출물이며 원본 My_core의 실행/합성 작업을 재개하지 않는다.
'''
(ROOT/'docs/CACHE_CYCLE_ANALYSIS.md').write_text(analysis,encoding='utf-8')

p=ROOT/'docs/VALIDATION.md';text=p.read_text(encoding='utf-8')
text=text.replace('diagnostic 346개','diagnostic '+str(read('out/elaboration.json')['diagnostics'])+'개')
text=text.replace('**52 checks PASS**','**'+str(checks('rv23_memory_tb'))+' checks PASS**')
text=text.replace('**1,058 checks PASS**','**'+f"{checks('rv23_cache_fault_tb'):,}"+' checks PASS**')
text=re.sub(r'^\| cache/SRAM 기본.*$',
    '| cache/SRAM 기본 | **'+str(checks('rv23_memory_tb'))+' checks PASS** | I128/D64 1-cycle hit, dual bank/동일 bank 중재, 연속 fetch, snoop/refill/FENCE.I/held-response 경합, word 단위 진행 |',text,flags=re.M)
text=re.sub(r'^\| cache fault/capacity.*$',
    '| cache fault/capacity | **'+f"{checks('rv23_cache_fault_tb'):,}"+' checks PASS** | 512 lines × 8 words 전체 32 KiB, error/부분 refill, final beat, snoop/refill bank-write 충돌 |',text,flags=re.M)
old_note='''- 모든 SRAM store가 I/D 캐시 전체를 지우던 동작을 실제 쓰기 수락 주소의 64-byte
  라인만 무효화하도록 바꿨다. CPU/debug 모두 적용하며 다른 tag의 alias는 유지한다.
  해당 라인의 lookup/히트 판정/마지막 refill 응답과 겹치는 쓰기는 오래된 라인의
  설치를 취소한다. FENCE.I는 I-cache 전체를 무효화한다.'''
text=text.replace(old_note,'''- 직렬 IF adapter/LSU arbiter를 두-bank hit 경로로 바꿨다. I128/D64 hit는 1 cycle이며
  서로 다른 bank의 두 LSU read는 함께 처리한다. 같은 word 쓰기의 응답만 기다리며
  같은 line의 다른 word를 불필요하게 차단하지 않는다. 이전 넓은 lock의 실패도 재현했다.
- SRAM 쓰기는 I-cache의 해당 line을 무효화하고 D-cache의 resident word에는 실제
  data/byte strobe를 merge한다. write miss는 allocate하지 않는다. refill 중 해당
  line 쓰기/FENCE.I는 설치를 취소하고, snoop/refill bank-write 충돌은 backpressure로 처리한다.''')
start=text.index('## CoreMark');end=text.index('## 재현과 증거',start)
section=f'''## CoreMark — bank 처리량 복구

main AXI는 64 bit이고 각 L1은 64-bit 2-bank, 총 32 KiB다. I128/D64 hit는 1 cycle,
서로 다른 bank의 두 LSU hit는 동시에 처리한다. D-cache는 write-through/no-write-allocate를
유지하며 실제 SRAM write snoop의 byte strobe를 resident word에 merge한다.

upstream commit `1f483d5b8316753a742cbf5590caf5bd0a4e4777`, GCC 15.2 `-O2`,
RV32IMFC/ilp32f. 같은 ELF의 전후 결과이며 CRC `e9f5/e714/1fd7/8e3a`가 일치했다.

{table()}

{write_section}

{historical_section}

2회 timed instructions {two['after']['instructions']:,}, 10회 {ten['after']['instructions']:,}으로
각 전후가 동일했다. {control['instructions']:,}개 명령의 timed-body retire control metadata도
같았다. 명령별 `mcycle` 파생 값은 달라지므로 전체 데이터 동등성으로 표현하지 않는다.

기존 TIM의 IPC 1.316246은 별도 메모리 경로의 기록이며 현재 달성값이 아니다.
TIM과 비교할 때는 위 정정 표의 보존 ELF 결과를 사용한다.
현재도 AXI write-through 응답 대기와 single-beat refill은 남아 있다. 10회까지의
반복 추세 확인이며 warm-only 구간/공식 CoreMark score 또는 STA sign-off가 아니다.

9-cycle IF hit와 4-cycle D hit가 생긴 원인, 수정 전후의 commit 공백, 실제 bank 구조와
남은 한계는 [CACHE_CYCLE_ANALYSIS](CACHE_CYCLE_ANALYSIS.md)에 정리했다.
이전 전체 무효화/주소별 무효화 단계의 `out/performance/comparison.json`과
`out/performance/iterations/`는 보존한 과거 결과이며 현재 측정으로 취급하지 않는다.

'''
text=text[:start]+section+text[end:]
text=text.replace('python scripts/compare_cache_performance.py\npython scripts/run_coremark_iterations.py --iterations 10',
                  'python scripts/compare_banked_performance.py\npython scripts/check_banked_control_trace.py\npython scripts/save_verification_snapshot.py')
p.write_text(text,encoding='utf-8')

paths={'audit':'out/rv32_release_audit.json','block_backend':'out/regression/report.json',
    'programs':'out/programs/report.json','extended':'out/extended.json','bus_lock':'out/bus_lock_report.json',
    'sequence_negative':'out/sequence_credit_negative.json','runtime_inputs':'out/programs/runtime_inputs.json',
    'cache_performance':'out/performance/banked_after/report.json',
    'cache_word_lock_negative':'out/cache_word_lock_negative.json',
    'cache_launch_negative':'out/cache_launch_negative.json',
    'write_path_performance':'out/performance/write_path/report.json',
    'write_path_latency_before':'out/performance/memory_latency_wt_before/report.json',
    'latency_before':'out/performance/memory_latency_before/report.json',
    'latency_after':'out/performance/memory_latency_after/report.json'}
if historical_section:paths['historical_tim_same_elf']=historical_path
snapshot={'validation_date':validation_date,'target':audit['target'],
    **{k:read(v) for k,v in paths.items()},
    'runner_sha256':{p.name:sha(p) for p in sorted((ROOT/'scripts').glob('*.py'))}}
dump(ROOT/'docs/verification_snapshot.json',snapshot)
print('PASS current 6-gate snapshot and cache cycle analysis saved')

from pathlib import Path
import hashlib,json,re,shutil
ROOT=Path(__file__).resolve().parents[1];OLD=Path('C:/Users/강지민/Desktop/My_core')
if (ROOT/'tb/e2e/dpi/rv_host_dpi.sv').exists():
    raise SystemExit('One-time import already completed; preserve the fixed host driver and run run_programs.py instead')
def copy(rel,dest=None):
    target=ROOT/(dest or rel);target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(OLD/rel,target)
for name in ['rv_host_dpi.sv','rv_commit_trace_logger.sv','elf_loader.cpp']:
    copy('tb/e2e/dpi/'+name)
for name in ['bootrom_wait.hex','bootrom_host_jump.hex']:
    copy('tb/fixtures/bootrom/'+name)
copy('scripts/build_fp_conversion_vectors.py')
for folder in ['dv_arithmetic_smoke','riscv_dv_fp_stress']:
    files=list((OLD/'verification/tests'/folder).glob('*.S'))
    for file in files:copy(file.relative_to(OLD).as_posix(),'sw/imported/'+folder+'/'+file.name)
p=ROOT/'tb/e2e/dpi/rv_host_dpi.sv'
s=p.read_text(encoding='utf-8')
s=s.replace('if (HTIF_ENABLE && !load_failed_o)',
            'if (HTIF_ENABLE && $test$plusargs("htif") && !load_failed_o)')
p.write_text(s,encoding='utf-8')
# Vendor only pinned source inputs used by the existing CoreMark port.
upstream=Path('C:/rv_build/coremark-src')
names=['core_list_join.c','core_main.c','core_matrix.c','core_state.c','core_util.c','coremark.h','LICENSE.md']
vendor=ROOT/'sw/benchmarks/coremark/upstream';vendor.mkdir(exist_ok=True)
for name in names:shutil.copy2(upstream/name,vendor/name)
(vendor/'PROVENANCE.json').write_text(json.dumps({'repository':'https://github.com/eembc/coremark',
    'commit':'1f483d5b8316753a742cbf5590caf5bd0a4e4777',
    'files':{n:hashlib.sha256((vendor/n).read_bytes()).hexdigest() for n in names}},indent=2)+'\n')
print('Copied ELF host/loader/trace, ROM and software inputs; CoreMark source only, no previous results')

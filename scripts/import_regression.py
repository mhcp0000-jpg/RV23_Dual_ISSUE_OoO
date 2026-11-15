"""Import reusable verification inputs, never previous result/build trees."""
from pathlib import Path
import re,shutil,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
OLD=Path('C:/Users/강지민/Desktop/My_core')
if (ROOT/'config/regression.json').exists():
    raise SystemExit('One-time import already completed; preserve current inputs and run run_regression.py instead')
entries=[];excluded=[];copied=set()
def copy(rel):
    dest=ROOT/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(OLD/rel,dest);copied.add(rel)
for runner in ['run_unit_tests.ps1','run_block_tests.ps1']:
    content=(OLD/'scripts'/runner).read_text(encoding='utf-8-sig')
    # Literal hashtables describe the original default unit/block suite.
    for block in re.findall(r'@\{\s*Top\s*=\s*".*?\n\s*\}',content,re.S):
        top=re.search(r'Top\s*=\s*"([^"]+)"',block).group(1)
        files=[s for s in re.findall(r'"([^"]+\.sv)"',block)]
        if not files:continue
        absent=[s for s in files if s.startswith('rtl/') and not (ROOT/s).exists()]
        if absent:
            excluded.append({'top':top,'reason':'replaced TIM architecture','absent':absent});continue
        params=[]
        match=re.search(r'ParameterArgs\s*=\s*@\((.*?)\)',block,re.S)
        if match:params=re.findall(r'"(-G[^"]+)"',match.group(1))
        if any('$' in arg for arg in params):
            # Loop-generated variants are explicitly expanded below.
            continue
        for f in files:
            if f.startswith('tb/'):copy(f)
        entry={'name':top+('_'+re.sub(r'[^A-Za-z0-9]+','_',','.join(params)) if params else ''),
               'top':top,'files':files,'params':params}
        if entry not in entries:entries.append(entry)
def add(top,files,params=(),suffix=''):
    for f in files:
        if f.startswith('tb/'):copy(f)
    e={'name':top+suffix,'top':top,'files':files,'params':list(params)}
    if e not in entries:entries.append(e)
pkg=['rtl/rv_ooo_pkg.sv']
for name,module in [('rv_lsu_pipe_widths_tb','rv_lsu_pipe'),
                    ('rv_exec_result_buffer_depth2_tb','rv_exec_result_buffer')]:
    file='tb/unit/backend/'+name+'.sv'
    add(name,pkg+['rtl/backend/'+module+'.sv',file])
front=pkg+['rtl/frontend/'+n+'.sv' for n in ['rv_fetch_queue','rv_branch_predictor','rv_fetch_target_buffer','rv_frontend']]
add('rv_frontend_cross_block_tb',front+['tb/unit/frontend/rv_frontend_cross_block_tb.sv'])
for params,suffix in [(['-GXLEN=64'],'_xlen64'),
                     (['-GXLEN=64','-GPADDR_WIDTH=32'],'_xlen64_pa32')]:
    add('rv_frontend_cross_block_tb',front+['tb/unit/frontend/rv_frontend_cross_block_tb.sv'],params,suffix)
for top in ['rv_lsu_base_cache_tb','rv_lsu_base_cache64_tb']:
    add(top,pkg+['rtl/backend/rv_issue_queue.sv','tb/unit/backend/rv_lsu_base_cache_tb.sv'])
for latency in [2,5,6]:
    add('rv_fpu_tb',pkg+['rtl/backend/rv_fpu.sv','tb/unit/backend/rv_fpu_tb.sv'],
        [f'-GFpuLatency={latency}'],f'_latency{latency}')
for width in [32,64]:
    add('rv_pmp_tb',pkg+['rtl/backend/rv_pmp.sv','tb/unit/backend/rv_pmp_tb.sv'],
        [f'-GPADDR_WIDTH={width}'],f'_pa{width}')
    add('rv_exec_result_buffer_depth2_tb',pkg+['rtl/backend/rv_exec_result_buffer.sv',
        'tb/unit/backend/rv_exec_result_buffer_depth2_tb.sv'],[f'-GXLEN={width}'],f'_xlen{width}')
for ports in [2,3,4,6]:
    add('rv_issue_arbiter_equiv_tb',pkg+['rtl/backend/rv_issue_arbiter.sv',
        'tb/unit/backend/rv_issue_arbiter_equiv_tb.sv'],[f'-GExecPorts={ports}'],f'_ports{ports}')
for early in [0,1]:
    add('rv_lsq_tb',pkg+['rtl/backend/rv_lsq.sv','tb/unit/backend/rv_lsq_tb.sv'],
        [f'-GEarlyLoadSelect={early}','-GAguLoadBypass=1'],f'_early{early}_agu1')
copy('tb/integration/backend/rv_backend_int_tb.sv')
corefiles=(ROOT/'rtl/filelist.f').read_text().splitlines()
backend=[s for s in corefiles if s=='rtl/rv_ooo_pkg.sv' or s.startswith('rtl/backend/') or
         s=='rtl/frontend/rv_c_expander.sv']
for params,suffix in [([],''),(['-GDivStressOnly=1'],'_div_stress')]:
    add('rv_backend_int_tb',backend+['tb/integration/backend/rv_backend_int_tb.sv'],params,suffix)
for file in ['scripts/gen_fpu_diff_vectors.py','tb/fixtures/bootrom/bootrom_test.hex']:
    copy(file)
for folder in ['sw/tests','sw/benchmarks/coremark']:
    for p in (OLD/folder).rglob('*'):
        if p.is_file() and p.suffix not in ['.elf','.bin','.o','.log','.json','.csv']:
            copy(p.relative_to(OLD).as_posix())
for name in ['build_rv32_smoke_elf.ps1','build_rv32c_smoke_elf.ps1','build_rv32_priv_smoke_elf.ps1']:
    copy('scripts/'+name)
# Preserve the exact oracle corpus settings used by the former FP corner run.
add('rv_fpu_diff_tb',pkg+['rtl/backend/rv_fpu.sv','tb/unit/backend/rv_fpu_diff_tb.sv'])
manifest={'cases':entries,'excluded':excluded,'scope':'Reusable original unit/block/backend regressions plus exact FP; TIM TBs superseded',
          'imported_inputs':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(copied)}}
(ROOT/'config').mkdir(exist_ok=True)
(ROOT/'config/regression.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('Imported',len(entries),'cases;',len(copied),'verification input files; excluded',len(excluded),'TIM cases')

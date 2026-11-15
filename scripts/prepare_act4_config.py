# SPDX-License-Identifier: Apache-2.0
"""Prepare a full RVA23S64 ACT4 configuration for the existing SoC."""
import copy,json,re,sys
from pathlib import Path
from ruamel.yaml import YAML
import pyjson5

ROOT=Path(__file__).resolve().parents[1]
vendor=ROOT/'third_party/riscv-arch-test'
template=vendor/'config/sail/sail-RVA23S64'
folder=ROOT/'config/act4/rv23';folder.mkdir(parents=True,exist_ok=True)
yaml=YAML();cfg=yaml.load((template/'sail-RVA23S64.yaml').read_text(encoding='utf-8'))
cfg['name']='rv23-RVA23S64';cfg['description']='Dual-issue OoO RVA23 SoC: PA32, I/D 32KiB, AXI64, SRAM1MiB'
p=cfg['params']
p.update(dict(PHYS_ADDR_WIDTH=32,NUM_PMP_ENTRIES=16,NUM_USABLE_PMP_ENTRIES=8,
    ARCH_ID_VALUE=0,IMP_ID_VALUE=0,VENDOR_ID_BANK=0,VENDOR_ID_OFFSET=0,
    MUTABLE_MISA_B=False,PMLEN=7,NUM_EXTERNAL_GUEST_INTERRUPTS=0,
    LRSC_RESERVATION_STRATEGY='reserve naturally-aligned 64-byte region',
    LRSC_MISALIGNED_BEHAVIOR='always raise misaligned exception',
    MISALIGNED_MAX_ATOMICITY_GRANULE_SIZE=8,MISALIGNED_SPLIT_STRATEGY='custom',
    ZAWRS_NTO_IS_NOP=False))
p['MARCHID_IMPLEMENTED']=False;p.pop('ARCH_ID_VALUE',None)
p['MIMPID_IMPLEMENTED']=False;p.pop('IMP_ID_VALUE',None)
p['HPM_EVENTS']=[0,1,2,3,4]
p['LRSC_FAIL_ON_NON_EXACT_LRSC']=True
old_overlay=folder/'overlay/isa/param/NUM_EXTERNAL_GUEST_INTERRUPTS.yaml'
if old_overlay.exists():old_overlay.unlink()
overlay=folder/'overlay/param';overlay.mkdir(parents=True,exist_ok=True)
(overlay/'NUM_EXTERNAL_GUEST_INTERRUPTS.yaml').write_text(
    '# SPDX-License-Identifier: BSD-3-Clause-Clear\n'
    '# H 1.0 permits GEILEN=0 (ISA manual 20240411, hypervisor section).\n'
    'schema:\n  minimum: 0\n',encoding='utf-8')
cfg['arch_overlay']='C:/rv_workspaces/rv23/config/act4/rv23/overlay'
for key in ['SCOUNTENABLE_EN','MCOUNTENABLE_EN','HCOUNTENABLE_EN']:
    p[key]=[index<7 for index in range(32)]
p['HPM_COUNTER_EN']=[3<=index<7 for index in range(32)]
p['COUNTINHIBIT_EN']=[index in [0,2,3,4,5,6] for index in range(32)]
with (folder/'rv23.yaml').open('w',encoding='utf-8') as stream:yaml.dump(cfg,stream)

base=pyjson5.loads((template/'sail.json').read_text(encoding='utf-8'))
current=json.loads((ROOT/'config/reference/sail-rv23.json').read_text(encoding='utf-8'))
def common(old,new):
    for key in old:
        if key not in new:continue
        if key=='regions':continue
        if isinstance(old[key],dict) and isinstance(new[key],dict):common(old[key],new[key])
        elif not isinstance(old[key],dict) and type(old[key])==type(new[key]):old[key]=copy.deepcopy(new[key])
common(base,current)
base.pop('$schema',None)
base['memory']['misaligned']['exceptions']['lrsc']='AlignmentException'
if 'hcounteren_writable_bits' in base['base']:
    base['base']['hcounteren_writable_bits']['value']='0x0000007f'
base['memory']['regions'][0]['attributes']['executable']=True
base['memory']['regions'][1]['size']['value']='0x10000'
for key in ['load_store','vector']:
    base['memory']['regions'][1]['attributes']['misaligned_exceptions'][key]={'Some':'AlignmentException'}
for address,size in [('0x0c000000','0x400000'),('0x10000000','0x1000'),('0x30000000','0x1000')]:
    io=copy.deepcopy(base['memory']['regions'][1]);io['base']['value']=address;io['size']['value']=size
    base['memory']['regions'].append(io)
base['memory']['regions'].sort(key=lambda region:int(region['base']['value'].replace('_',''),0))
for region in base['memory']['regions']:
    if region['attributes']['mem_type']=='MainMemory':
        region['size']['value']='0x100000';region['attributes']['atomic_support']='AMOArithmetic'
        region['attributes']['misaligned_atomicity_granule_size_exp']=0
        region['attributes']['vector_misaligned_atomicity_granule_size_exp']=0
base['platform']['simple_interrupt_generator']={'supported':True,'base':0x30000000}
(folder/'sail-0.13.1-incompatible-H.json').write_text(json.dumps(base,indent=2)+'\n',encoding='utf-8')
base=copy.deepcopy(current)
io=copy.deepcopy(base['memory']['regions'][1]);io['base']['value']='0x30000000';io['size']['value']='0x1000'
base['memory']['regions'].append(io)
base['memory']['regions'].sort(key=lambda region:int(region['base']['value'].replace('_',''),0))
base['platform']['simple_interrupt_generator']={'supported':True,'base':0x30000000}
(folder/'sail.json').write_text(json.dumps(base,indent=2)+'\n',encoding='utf-8')

link=(vendor/'config/sail/sail-rv64-max/link.ld').read_text(encoding='utf-8')
link=link.replace('RAM_LENGTH = 0x80000000;','RAM_LENGTH = 0x100000;')
link=link.replace('  _end = .;','  _end = .;\n  .tohost 0x800ff000 : { KEEP(*(.tohost)) } > ram')
link=link.replace('_end <= ORIGIN(ram) + LENGTH(ram)','_end <= 0x800ff000')
(folder/'link.ld').write_text(link,encoding='utf-8')
macros=(vendor/'config/sail/sail-rv64-max/rvmodel_macros.h').read_text(encoding='utf-8')
def macro(name,body):
    global macros
    pattern=r'^#define '+re.escape(name)+r'[^\n]*(?:\n[^\n]*)*?(?=\n\n)'
    replacement='#define '+name+' \\\n'+' \\\n'.join('  '+line for line in body)+'\n'
    macros,count=re.subn(pattern,lambda _:replacement,macros,count=1,flags=re.M)
    assert count==1,name
macro('RVMODEL_HALT_PASS',['li t0,0x10000000;','sw zero,0x14(t0);','1:j 1b;'])
macro('RVMODEL_HALT_FAIL',['li t0,0x10000000;','li t1,1;','sw t1,0x14(t0);','1:j 1b;'])
macro('RVMODEL_IO_WRITE_STR(_R1, _R2, _R3, _STR_PTR)',[
    'li _R2,0x10000018;','1:lbu _R1,0(_STR_PTR);','beqz _R1,2f;',
    'sw _R1,0(_R2);','addi _STR_PTR,_STR_PTR,1;','j 1b;','2:'])
macro('RVMODEL_SET_MEXT_INT(_R1, _R2)',[
    'li _R2,0x0c000004;','li _R1,1;','sw _R1,0(_R2);',
    'li _R2,0x0c002000;','li _R1,2;','sw _R1,0(_R2);',
    'li _R2,0x0c200000;','sw zero,0(_R2);',
    'li _R2,0x10000008;','li _R1,0x101;','sw _R1,0(_R2);'])
macro('RVMODEL_CLR_MEXT_INT(_R1, _R2)',[
    'li _R2,0x10000008;','li _R1,1;','sw _R1,0(_R2);',
    'li _R2,0x0c200004;','lw _R1,0(_R2);','sw _R1,0(_R2);'])
for label,bit in [('SEXT',9),('SSW',1)]:
    macro('RVMODEL_SET_'+label+'_INT(_R1, _R2)',[f'li _R1,{1<<bit};','csrs mip,_R1;'])
    macro('RVMODEL_CLR_'+label+'_INT(_R1, _R2)',[f'li _R1,{1<<bit};','csrc mip,_R1;'])
macros=macros.replace('#define RVMODEL_INTERRUPT_LATENCY 1','#define RVMODEL_INTERRUPT_LATENCY 128')
(folder/'rvmodel_macros.h').write_text(macros,encoding='utf-8')
test=dict(name='rv23-RVA23S64',compiler_exe='C:/rv_toolchains/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc.exe',
    objdump_exe='C:/rv_toolchains/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-objdump.exe',
    ref_model_exe='C:/rv_workspaces/rv23/out/act4/sail-0.16/sail_act4_reference.exe',ref_model_type='sail',
    udb_config='rv23.yaml',linker_script='link.ld',dut_include_dir='.')
with (folder/'test_config.yaml').open('w',encoding='utf-8') as stream:yaml.dump(test,stream)
print('PREPARED full RVA23S64 ACT4 DUT configuration',folder,flush=True)

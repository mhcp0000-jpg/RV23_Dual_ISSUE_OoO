"""Configure official Sail 0.16 for the implemented RVA23 core choices."""
import copy
import argparse
import json
import os
import re
from pathlib import Path
from sim_runner import ROOT, Simulator, sha, dump

parser=argparse.ArgumentParser()
parser.add_argument('--validate',action='store_true')
args=parser.parse_args()

template = ROOT/'out/reference/sail-riscv-0.16-cygwin/build/config/rv64d_v128_e64.json'
text = template.read_text(encoding='utf-8')
text = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
              lambda match: '' if match[0].startswith('/') else match[0], text)
config = json.loads(text)
inventory = json.loads((ROOT/'config/rva23_required_extensions.json').read_text(encoding='utf-8'))
names = {name for key, values in inventory.items() if key.startswith('mandatory_') or key=='Sha_components'
         for name in values}
names |= {'S','U','Zca','Zcd','Zmmul','Zaamo','Zalrsc','Zba','Zbb','Zbs'}
for name, fields in config['extensions'].items():
    if 'supported' in fields: fields['supported'] = name in names
    if 'mutable_misa' in fields: fields['mutable_misa'] = False
base = config['base']
for name in ['writable_hpm_counters','scounteren_writable_bits','mcounteren_writable_bits']:
    base[name]['value'] = '0x0000007f'
base['medeleg']['delegatable_bits']['value'] = '0x0000000000f0b7ff'
base['mideleg']['delegatable_bits']['value'] = '0x0000000000002222'
memory = config['memory']
memory['physaddr_bits'] = 32
memory['pmp']['count'] = 16
memory['pmp']['usable_count'] = 8
memory['misaligned']['exceptions']['amo'] = {'Some':'AlignmentException'}
memory['misaligned']['exceptions']['lrsc'] = {'Some':'AlignmentException'}
memory['regions'][0]['attributes']['executable'] = True
memory['regions'][1]['size']['value'] = '0x10000'
for kind in ['load_store','vector']:
    memory['regions'][1]['attributes']['misaligned_exceptions'][kind] = {'Some':'AlignmentException'}
io_region = copy.deepcopy(memory['regions'][1])
io_region['base']['value'] = '0x0c000000'
io_region['size']['value'] = '0x400000'
host_region = copy.deepcopy(io_region)
host_region['base']['value'] = '0x10000000'
host_region['size']['value'] = '0x1000'
ram = memory['regions'][2]
ram['size']['value'] = '0x100000'
ram['attributes']['atomic_support'] = 'AMOArithmetic'
ram['attributes']['misaligned_atomicity_granule_size_exp'] = 0
ram['attributes']['vector_misaligned_atomicity_granule_size_exp'] = 0
memory['regions'][1:1] = [io_region,host_region]
memory['regions'].sort(key=lambda region:int(region['base']['value'],0))
platform = config['platform']
platform['reservation']['reservation_set_size_exp'] = 6
platform['reservation']['require_exact_reservation_addr'] = True
platform['reservation']['invalidate_on_same_hart_store'] = True
platform['simple_interrupt_generator']['supported'] = False
platform['simple_interrupt_generator']['base'] = 0
platform['event_selectors'] = []  # Implementation-specific RTL HPM event codes are tested separately.
h = config['extensions']['H']
h['geilen'] = 0
for modes, allowed in [('hgatp_modes','Sv39x4'),('vsatp_modes','Sv39')]:
    for mode in h[modes]: h[modes][mode] = mode == allowed
# The core writes zero transformed instructions except the required implicit-PTE
# pseudoinstruction, which the model handles independently of these switches.
for cause in h['transformed_instruction']: h['transformed_instruction'][cause] = False
v = config['extensions']['V']
v['vstart']['zero_required'] = {'arith':False,'scalar_move':False}
config['extensions']['Ssnpm']['supported_pmlen_16'] = False
stateen = config['extensions']['Stateen']
stateen['Smstateen']['supported'] = False
stateen['Ssstateen']['supported'] = True
for bank in ['mstateen0','hstateen0','sstateen0']:
    for bit in stateen[bank]:
        if bit not in ['SE0','ENVCFG']: stateen[bank][bit] = 'CSRBit_ReadOnlyZero'
path = ROOT/'config/reference/sail-rv23.json'
dump(path, config)
report=dict(
    passed=False, scope='DUT configuration preparation; validation by the Sail model is required',
    generator_sha256=sha(__file__), template_sha256=sha(template), config_sha256=sha(path),
    enabled_extensions=sorted(names), limitations=[
        'PLIC/HostIF device behavior and cycle/time values are not differential oracles',
        'Implementation-defined HPM event selection is validated by dedicated RTL tests',
        'A configured reference is not architectural certification'])
if args.validate:
    build=json.loads((ROOT/'out/reference/sail-riscv-0.16-cygwin/build_report.json').read_text(encoding='utf-8'))
    binary=ROOT/build['binary'];assert build['passed'] and sha(binary)==build['binary_sha256']
    with Simulator() as sim:
        sim.env['PATH']='C:/rv_toolchains/cygwin-rv23/bin;'+os.environ['PATH']
        report['validation'],output=sim.run([binary,'--config',path,'--validate-config'],
            ROOT/'out/reference/sail_config_validation.log',30)
        assert 'PASS Sail model configuration' in output
    report['passed']=True;report['reference_binary_sha256']=sha(binary)
dump(ROOT/'out/reference/sail_config_provenance.json',report)
print('PREPARED', path.relative_to(ROOT), flush=True)

"""Run the already-preserved historical TIM ELF on the current cached RV32 SoC.

Never rebuild or replace the ELF; never run or modify the old My_core project.
"""
import json,re
from sim_runner import ROOT,Simulator,sha,dump
folder=ROOT/'out/performance/tim_reference_elf'
path=folder/'report.json';old=json.loads(path.read_text(encoding='utf-8'))
elf=ROOT/old['elf'];digest=sha(elf)
assert digest==old['elf_sha256']=='33fe48d15f11a4a396d821fa1feecac527e8322a6af61b8797debb2f02af69ac'
assert sha(ROOT/old['historical_report'])==old['historical_report_sha256']
model=json.loads((ROOT/'out/programs/model.json').read_text(encoding='utf-8'))
assert '-GXLEN=32' in model['params']
for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
assert sha(ROOT/model['binary'])==model['binary_sha256']
rom=ROOT/'tb/fixtures/bootrom/bootrom_host_jump.hex';rom_hash=sha(rom)
with Simulator() as sim:
    run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
        '+trace_file=NUL','+quiet_commit','+timeout_cycles=20000000','+expected_exit_code=0'],folder/'simulation.log',600)
    assert 'ELF AXI readback PASS' in text and 'PASS rv32_program_tb' in text
    values=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([0-9a-fA-F]{8})\]',text)]
    start=values.index(0x434d0001);packet=values[start:start+12]
    assert len(packet)==12 and packet[6:10]==[0xe9f5,0xe714,0x1fd7,0x8e3a] and packet[11]&0x17==1
    cycles=packet[2]+(packet[3]<<32);instructions=packet[4]+(packet[5]<<32)
    assert instructions==old['historical_tim']['instructions']
    for p,h in model['inputs'].items():assert sha(ROOT/p)==h,p
    assert sha(elf)==digest and sha(rom)==rom_hash
    result={**old,'passed':True,'model_inputs':model['inputs'],'binary':model['binary'],
        'binary_sha256':model['binary_sha256'],'run':run,
        'current_cache':{'cycles':cycles,'instructions':instructions,'ipc':instructions/cycles,'packet':packet},
        'runtime_inputs':{'tb/fixtures/bootrom/bootrom_host_jump.hex':rom_hash},'runner_sha256':sha(__file__)}
    dump(path,result)
print('PASS preserved TIM ELF on current cache:',instructions,'instructions,',cycles,'cycles; no ELF rebuild',flush=True)

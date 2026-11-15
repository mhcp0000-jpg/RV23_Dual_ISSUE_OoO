"""Longer CoreMark runs on the unchanged, already validated cached SoC model.

Keeps the 22-case correctness report intact. Only ITERATIONS differs from its
CoreMark compiler arguments; checks raw CRC/status and source/binary hashes.
"""
import argparse,json,re
from sim_runner import ROOT,Simulator,GCC,sha,dump

parser=argparse.ArgumentParser()
parser.add_argument('--iterations',nargs='+',type=int,default=[10])
args=parser.parse_args()
assert all(2<=n<=1000 for n in args.iterations)
base=json.loads((ROOT/'out/programs/report.json').read_text())
case=next(c for c in base['cases'] if c['name']=='coremark')
assert base['passed'] and case['passed']
model=json.loads((ROOT/'out/programs/model.json').read_text())
def fresh():
    assert sha(ROOT/model['binary'])==model['binary_sha256']
    for path,digest in model['inputs'].items():assert sha(ROOT/path)==digest,path
    for path,digest in case['program']['inputs'].items():assert sha(ROOT/path)==digest,path
    rom=base['runtime_inputs']
    assert sha(ROOT/rom['bootrom_file'])==rom['bootrom_sha256']
fresh()
root=ROOT/'out/performance/iterations'
report={'passed':False,'state':'running','model':model,
    'runtime_inputs':base['runtime_inputs'],
    'baseline':{'iterations':2,**case['coremark'],'run':case['run']},'cases':[],
    'scope':'Cold start each run, identical source/flags except ITERATIONS; compare amortization, not warm-only IPC or certified score'}
output=root/'report.json';dump(output,report)
with Simulator() as sim:
    for iterations in args.iterations:
        folder=root/f'iter_{iterations}';folder.mkdir(parents=True,exist_ok=True)
        elf=folder/'test.elf'
        flags=[f'-DITERATIONS={iterations}' if x.startswith('-DITERATIONS=') else x
               for x in case['program']['compiler_args']]
        build,_=sim.run([GCC/'riscv-none-elf-gcc.exe',*flags,'-o',elf],folder/'compile.log',60)
        digest=sha(elf)
        print('RUN cached SoC CoreMark iterations='+str(iterations),flush=True)
        # Full instruction formatting goes to the Windows null device; this
        # performance run retains CRC, timed counters and TB cache statistics.
        run,text=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            '+trace_file=NUL','+quiet_commit',f'+timeout_cycles={iterations*10000000}',
            '+expected_exit_code=0'],folder/'simulation.log',max(600,iterations*90))
        fresh();assert sha(elf)==digest
        assert 'ELF AXI readback PASS' in text and 'PASS rv32_program_tb' in text
        values=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([0-9a-fA-F]{8})\]',text)]
        start=values.index(0x434d0001);packet=values[start:start+12]
        assert len(packet)==12 and packet[1]==iterations
        assert packet[6:10]==case['coremark']['packet'][6:10] and packet[11]&0x17==1,packet
        cycles=packet[2]+(packet[3]<<32);instructions=packet[4]+(packet[5]<<32)
        assert cycles>0 and instructions>0
        counters=re.search(r'CACHE_PERF (.*)',text);assert counters
        result={'iterations':iterations,'passed':True,'elf':elf.relative_to(ROOT).as_posix(),
            'elf_sha256':digest,'software_inputs':case['program']['inputs'],
            'compiler_args':flags,'compile':build,'run':run,'packet':packet,
            'cycles':cycles,'instructions':instructions,'ipc':instructions/cycles,
            'cycles_per_iteration':cycles/iterations,
            'whole_program_cache':{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',counters[1])}}
        report['cases'].append(result);dump(output,report)
        print('PASS iterations',iterations,'cycles',cycles,'IPC',result['ipc'],flush=True)
report.update(passed=True,state='finished');dump(output,report)
print('PASS CoreMark iteration comparison',flush=True)

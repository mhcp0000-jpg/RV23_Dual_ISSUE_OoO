"""Compare unchanged full-core vector probes with the saved pre-fastpath binary."""
import json,re
from sim_runner import ROOT,Simulator,GCC,dump,sha,source_inputs

folder=ROOT/'out/performance/vector_latency';folder.mkdir(parents=True,exist_ok=True)
before=json.loads((ROOT/'out/performance/vector_fastpath_before/model.json').read_bytes())
after=json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_bytes())
assert before['params']==after['params']
assert after['inputs']==source_inputs(after['inputs'])
for model in [before,after]:assert sha(ROOT/model['binary'])==model['binary_sha256']
cases=[
    ('scalar_add',['addi a0,a0,1'],['li a0,7'],['li t0,263','bne a0,t0,fail']),
    ('vset',['vsetivli a2,2,e64,m1,tu,mu'],[],['li t0,2','bne a2,t0,fail']),
    ('vadd',['vadd.vv v8,v16,v24'],['vsetivli a2,2,e64,m1,tu,mu','vmv.v.i v16,2','vmv.v.i v24,3'],
     ['vmv.x.s t0,v8','li t1,5','bne t0,t1,fail']),
    ('vle64',['vle64.v v8,(s0)'],['vsetivli a2,2,e64,m1,tu,mu'],['vmv.x.s t0,v8','li t1,123','bne t0,t1,fail']),
    ('vle32',['vle32.v v8,(s0)'],['vsetivli a2,4,e32,m1,tu,mu'],['vmv.x.s t0,v8','li t1,123','bne t0,t1,fail']),
    ('vluxei64',['vluxei64.v v8,(s0),v4'],['vsetivli a2,2,e64,m1,tu,mu','vid.v v4','vsll.vi v4,v4,3'],
     ['vmv.x.s t0,v8','li t1,123','bne t0,t1,fail']),
    ('vslidedown',['vslidedown.vi v8,v16,1'],['vsetivli a2,2,e64,m1,tu,mu','vmv.v.i v16,2'],
     ['vmv.x.s t0,v8','li t1,2','bne t0,t1,fail']),
]
lines=['.section .text.init,"ax"','.option norvc','.option norelax','.globl _start','_start:',
       'la t0,fail','csrw mtvec,t0','li t0,0x02000000','sw zero,0(t0)',
       'li t0,0x600','csrs mstatus,t0','la s0,data','li s1,0x10000000']
for index,(name,body,setup,checks) in enumerate(cases):
    lines += [*setup,f'call {name}','csrr s7,mcycle',f'call {name}','csrr s8,mcycle',
              'sub s8,s8,s7',*checks,f'li t0,0x{0x564c4100+index:08x}','sw t0,12(s1)','sw s8,12(s1)']
lines += ['sw zero,20(s1)','halt: j halt','fail: li t0,1','li t1,0x10000000','sw t0,20(t1)','j halt']
for name,body,setup,checks in cases:lines += ['.balign 64',name+':','.rept 128',*body,'.endr','ret']
lines += ['.section .data,"aw"','.balign 64','data: .dword 123,456']
source=folder/'test.S';source.write_text('\n'.join(lines)+'\n',encoding='utf-8')
elf=folder/'test.elf';linker='scripts/reference/upstream_htif.ld'
inputs=source_inputs([source.relative_to(ROOT).as_posix(),linker,'tb/fixtures/bootrom/bootrom_host_jump64.hex'])
results={}
with Simulator() as sim:
    compile_run,_=sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcv','-mabi=lp64d',
        '-mcmodel=medany','-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
        '-T',linker,source,'-o',elf],folder/'compile.log',120)
    digest=sha(elf)
    for label,model in [('before',before),('after',after)]:
        run,log=sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            '+quiet_commit','+timeout_cycles=200000','+expected_exit_code=0'],folder/(label+'.log'),300)
        assert 'PASS rv32_program_tb' in log and sha(elf)==digest
        words=[int(v,16) for v in re.findall(r'\[host-event kind=0 data=0x([\da-fA-F]{8})\]',log)]
        assert len(words)==2*len(cases) and words[::2]==list(range(0x564c4100,0x564c4100+len(cases)))
        results[label]=dict(model=model,run=run,cycles=dict(zip([c[0] for c in cases],words[1::2])))
assert after['inputs']==source_inputs(after['inputs']) and inputs==source_inputs(inputs)
old,new=results['before']['cycles'],results['after']['cycles']
assert new['scalar_add']==old['scalar_add'] and new['vadd']<old['vadd'] and new['vluxei64']<old['vluxei64']
measured=[dict(name=c[0],operations=128,before_cycles=old[c[0]],after_cycles=new[c[0]],
    cycle_reduction_percent=100*(old[c[0]]-new[c[0]])/old[c[0]]) for c in cases]
dump(folder/'report.json',dict(passed=True,scope='Warmed full-core probes, 128 vector instructions; includes frontend/call/CSR overhead, not isolated FU latency or CoreMark',
    driver_sha256=sha(__file__),inputs=inputs,elf_sha256=digest,compile=compile_run,results=results,cases=measured))
for case in measured:print(case,flush=True)
print('PASS exact-ELF full-core vector latency comparison',flush=True)

"""Check guest load extension and store byte enables in HS and HU-enabled U."""
import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha


def width_checks(guest_address):
    initial = 0x89ABCDEF8123FE80
    lines = [
        '  li s1,0x800a0020', f'  li s2,{guest_address:#x}',
        f'  li t0,{initial:#x}', '  sd t0,0(s1)',
    ]
    for suffix, width, signed in [
        ('b',8,True), ('bu',8,False), ('h',16,True), ('hu',16,False),
        ('w',32,True), ('wu',32,False), ('d',64,False),
    ]:
        value = initial & ((1 << width)-1)
        if signed and value >> (width-1):
            value -= 1 << width
        lines += [f'  hlv.{suffix} t0,(s2)', f'  li t1,{value}',
                  '  bne t0,t1,fail']
    for suffix, width in [('b',8), ('h',16), ('w',32), ('d',64)]:
        mask = (1 << width)-1
        stored = 0xFEDCBA9876543210
        value = (initial & ~mask) | (stored & mask)
        lines += [f'  li t0,{initial:#x}', '  sd t0,0(s1)',
                  f'  li t0,{stored:#x}', f'  hsv.{suffix} t0,(s2)',
                  '  ld t0,0(s1)', f'  li t1,{value:#x}', '  bne t0,t1,fail']
    # HLVX uses execute permission and an unmasked address.
    lines += [f'  li t0,{initial:#x}', '  sd t0,0(s1)',
              '  li s2,0x400a0020', '  hlvx.hu t0,(s2)',
              '  li t1,0xfe80', '  bne t0,t1,fail',
              '  hlvx.wu t0,(s2)', '  li t1,0x8123fe80', '  bne t0,t1,fail']
    return '\n'.join(lines)+'\n'


def main():
    source_base = ROOT/'sw/tests/rv64_hypervisor_access.S'
    runtime = {path:sha(ROOT/path) for path in [
        'sw/tests/rv64_hypervisor_access.S', 'sw/benchmarks/coremark/rv32_tim.ld',
        'tb/fixtures/bootrom/bootrom_host_jump64.hex']}
    model = json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    assert all(flag in model['params'] for flag in ['-GXLEN=64','-GHAS_H=1','-GHAS_V=1'])
    inputs = {**model['inputs'], **runtime, model['binary']:model['binary_sha256']}
    for path, digest in inputs.items():
        assert sha(ROOT/path)==digest, path
    code = source_base.read_text(encoding='utf-8')
    for anchor, address in [('  la t0,u_entry\n',0x400a0020),
                            ('  li s7,3\n',0xfe000000400a0020)]:
        assert code.count(anchor)==1
        code = code.replace(anchor,width_checks(address)+anchor)
    folder = ROOT/'out/rva23/hypervisor_access_widths'
    folder.mkdir(parents=True,exist_ok=True)
    source, elf, trace = (folder/name for name in ['test.S','test.elf','commit.csv'])
    source.write_text(code,encoding='utf-8')
    with Simulator() as sim:
        compile_run,_ = sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh','-mabi=lp64d',
            '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
            '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
        run, text = sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
            '+timeout_cycles=300000','+expected_exit_code=0'],folder/'simulation.log',120)
    assert 'PASS rv32_program_tb' in text and 'data=0x48595034' in text
    with trace.open(newline='') as stream:
        traps = [int(row['cause']) for row in csv.DictReader(stream)
                 if row['trap']=='1' and int(row['pc'],16)>=0x40000000]
    assert traps==[13,2,2,8],traps
    for path,digest in inputs.items():
        assert sha(ROOT/path)==digest,path
    dump(folder/'report.json',dict(passed=True,model=model,runtime_inputs=runtime,
         generator_sha256=sha(__file__),compile=compile_run,run=run,
         traps=traps,width_checks=26,artifacts={p.name:sha(p) for p in [source,elf,trace,folder/'simulation.log']}))
    print('PASS HS/U HLV, HLVX and HSV: 26 data checks and 4 expected traps')


if __name__=='__main__':
    main()

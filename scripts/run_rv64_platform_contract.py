"""Exercise the inherited platform contract with the full RV64 H/V SoC."""
import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha


def main():
    original = ROOT/'sw/tests/rv32_system_contract.S'
    model = json.loads((ROOT/'out/rva23/hypervisor_integration/model.json').read_text(encoding='utf-8'))
    assert all(flag in model['params'] for flag in ['-GXLEN=64', '-GHAS_H=1', '-GHAS_V=1'])
    runtime = {path:sha(ROOT/path) for path in [
        'sw/tests/rv32_system_contract.S', 'sw/benchmarks/coremark/rv32_tim.ld',
        'tb/fixtures/bootrom/bootrom_host_jump64.hex']}
    inputs = {**model['inputs'], **runtime, model['binary']:model['binary_sha256']}
    for path, digest in inputs.items():
        assert sha(ROOT/path)==digest, path

    code = original.read_text(encoding='utf-8')
    first = code.index('  li s3,0')
    last = code.index('  # Resolve a taken branch', first)
    code = code[:first]+'''  csrr t0,misa
  srli t0,t0,62
  li t1,2
  bne t0,t1,fail
'''+code[last:]
    code = code.replace('  li t1,2\n  beq t0,t1,illegal\n','')
    first, last = code.index('illegal:\n'), code.index('software:\n')
    code = code[:first]+code[last:]
    for cause in [3,7,11]:
        code = code.replace(f'0x{0x80000000+cause:08x}', f'0x{(1<<63)+cause:016x}')
    anchor = '  li t0,0x800f0000\n'
    assert code.count(anchor)==1
    code = code.replace(anchor,'''  # Transfer interrupt delivery to S mode.
  li t0,-1
  csrw pmpaddr0,t0
  li t0,31
  csrw pmpcfg0,t0
  li t0,0x8000000000000000
  csrw menvcfg,t0
  li t0,2
  csrw mcounteren,t0
  la t0,supervisor_handler
  csrw stvec,t0
  li t0,0x220
  csrw mideleg,t0
  csrw mie,t0
  li t0,0x0c002000
  sw zero,0(t0)
  li t0,0x0c002080
  li t1,2
  sw t1,0(t0)
  li t0,0x1800
  csrc mstatus,t0
  li t0,0x800
  csrs mstatus,t0
  la t0,supervisor_entry
  csrw mepc,t0
  mret
supervisor_entry:
  csrsi sstatus,2
  csrw stimecmp,zero
wait_stip:
  li t0,4
  bne s0,t0,wait_stip
  li t0,0x10000000
  li t1,0x101
  sw t1,8(t0)
wait_seip:
  li t0,5
  bne s0,t0,wait_seip
  csrci sstatus,2
'''+anchor)
    code = code.replace('0x52563332','0x52563634')
    anchor = 'fail:\n'
    assert code.count(anchor)==1
    code = code.replace(anchor,'''.balign 4
supervisor_handler:
  csrr t0,scause
  li t1,0x8000000000000005
  beq t0,t1,supervisor_timer
  li t1,0x8000000000000009
  bne t0,t1,fail
  li t0,4
  bne s0,t0,fail
  li t0,0x0c201004
  lw t1,0(t0)
  li t2,1
  bne t1,t2,fail
  li t2,0x10000000
  li t1,0x201
  sw t1,8(t2)
  li t1,1
  sw t1,0(t0)
  addi s0,s0,1
  sret
supervisor_timer:
  li t0,3
  bne s0,t0,fail
  li t0,-1
  csrw stimecmp,t0
  addi s0,s0,1
  sret
'''+anchor)
    # A failure from either privilege must report failure through HostIF.
    code = code.replace('fail:\n  csrci mstatus,8\n','fail:\n')
    folder = ROOT/'out/rva23/rv64_platform_contract'
    folder.mkdir(parents=True,exist_ok=True)
    source, elf, trace = (folder/name for name in ['test.S','test.elf','commit.csv'])
    source.write_text(code,encoding='utf-8')
    with Simulator() as sim:
        compile_record, _ = sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh_sstc','-mabi=lp64d',
            '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
            '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
        run, text = sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit','+debug_check',
            '+timeout_cycles=300000','+expected_exit_code=0'],folder/'simulation.log',120)
    assert 'PASS rv32_program_tb' in text and 'data=0x52563634' in text
    assert 'NATIVE DEBUG PASS halt/drain/read/write/resume' in text
    with trace.open(newline='') as stream:
        traps = [int(row['cause']) for row in csv.DictReader(stream)
                 if row['trap']=='1' and int(row['pc'],16)>=0x80000000]
    assert traps==[3,7,11,5,9],traps
    for path,digest in inputs.items():
        assert sha(ROOT/path)==digest,path
    dump(folder/'report.json',dict(passed=True,model=model,runtime_inputs=runtime,
         generator_sha256=sha(__file__),compile=compile_record,run=run,
         traps=traps,source_sha256=sha(source),elf_sha256=sha(elf),trace_sha256=sha(trace)))
    print('PASS RV64 platform contract: M/S interrupts, PLIC claim/complete, FENCE.I and debug resume')


if __name__=='__main__':
    main()

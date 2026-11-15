"""Exercise an HS software save and restore of VS vector and FP state."""
import csv
import json

from sim_runner import GCC, ROOT, Simulator, dump, sha


def fixture(original):
    code = original.split('hs_entry:\n',1)[0]
    code += '''hs_entry:
  la t0,guest_entry
  li t1,0x40000000
  sub t0,t0,t1
  csrw sepc,t0
  li t0,0x180
  csrw hstatus,t0
  li t0,0x2300
  csrw sstatus,t0
  sret
guest_entry:
  li s7,1
  la t0,guest_vector
'''
    for register in range(0,32,8):
        code += f'  vl8re8.v v{register},(t0)\n  addi t0,t0,128\n'
    code += '  la t0,guest_fp\n'
    for register in range(32):
        code += f'  fld f{register},{register*8}(t0)\n'
    code += '''  vsetivli zero,5,e32,m2,ta,ma
  csrwi vcsr,5
  csrwi vstart,3
  li t0,0x67
  csrw fcsr,t0
  ecall
guest_resume:
  csrr t0,vstart
  li t1,3
  bne t0,t1,fail
  csrr t0,vl
  li t1,5
  bne t0,t1,fail
  csrr t0,vtype
  li t1,0xd1
  bne t0,t1,fail
  csrr t0,vcsr
  li t1,5
  bne t0,t1,fail
  csrr t0,fcsr
  li t1,0x67
  bne t0,t1,fail
  csrw vstart,zero
  la t0,vector_check
'''
    for register in range(0,32,8):
        code += f'  vs8r.v v{register},(t0)\n  addi t0,t0,128\n'
    code += '''  la t0,vector_check
  la t1,guest_vector
  li t2,64
check_words:
  ld t3,0(t0)
  ld t4,0(t1)
  bne t3,t4,fail
  addi t0,t0,8
  addi t1,t1,8
  addi t2,t2,-1
  bnez t2,check_words
  la t0,guest_fp
'''
    for register in range(32):
        code += f'  fmv.x.d t1,f{register}\n  ld t2,{register*8}(t0)\n  bne t1,t2,fail\n'
    code += '''  li s7,2
  ecall
stop:
  j stop
.balign 4
hs_trap:
  csrr t0,scause
  li t1,10
  bne t0,t1,fail
  csrr t0,hstatus
  andi t0,t0,0x180
  li t1,0x180
  bne t0,t1,fail
  li t0,2
  beq s7,t0,finish
  li t0,1
  bne s7,t0,fail
  csrr t0,vsstatus
  li t1,0x6600
  and t0,t0,t1
  bne t0,t1,fail
  csrr s1,vl
  csrr s2,vtype
  csrr s3,vstart
  csrr s4,vcsr
  csrr s5,fcsr
  csrw vstart,zero
  la t0,vector_save
'''
    for register in range(0,32,8):
        code += f'  vs8r.v v{register},(t0)\n  addi t0,t0,128\n'
    code += '  la t0,fp_save\n'
    for register in range(32):
        code += f'  fsd f{register},{register*8}(t0)\n'
    code += '  la t0,host_vector\n'
    for register in range(0,32,8):
        code += f'  vl8re8.v v{register},(t0)\n  addi t0,t0,128\n'
    code += '  li t0,-1\n'
    for register in range(32):
        code += f'  fmv.d.x f{register},t0\n'
    code += '''  vsetivli zero,2,e64,m1,tu,mu
  csrw vcsr,zero
  csrw fcsr,zero
  la t0,fp_save
'''
    for register in range(32):
        code += f'  fld f{register},{register*8}(t0)\n'
    code += '  la t0,vector_save\n'
    for register in range(0,32,8):
        code += f'  vl8re8.v v{register},(t0)\n  addi t0,t0,128\n'
    code += '''  vsetvl t0,s1,s2
  bne t0,s1,fail
  csrw vcsr,s4
  csrw fcsr,s5
  csrw vstart,s3
  csrr t0,sepc
  addi t0,t0,4
  csrw sepc,t0
  sret
finish:
  lui t0,0x10000
  li t1,0x56534354
  sw t1,0xc(t0)
  sw zero,0x14(t0)
  j stop
fail:
  lui t0,0x10000
  sw s7,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j stop
.section .data,"aw"
.balign 128
guest_vector:
'''
    code += ''.join(f'  .dword {0x8123456789abcdef ^ (index * 0x0101010101010101):#x}\n'
                    for index in range(64))
    code += 'guest_fp:\n'
    code += ''.join(f'  .dword {0x923456789abcdef0 + index:#x}\n' for index in range(32))
    code += '.balign 128\nhost_vector:.fill 512,1,0xff\n'
    code += original[original.index('.section .bss'):]
    return code+'''.balign 128
vector_save:.skip 512
vector_check:.skip 512
fp_save:.skip 256
'''


def main():
    base = ROOT/'sw/tests/rv64_hypervisor_basic.S'
    model_path = ROOT/'out/rva23/hypervisor_integration/model.json'
    model = json.loads(model_path.read_text(encoding='utf-8'))
    assert all(flag in model['params'] for flag in ['-GXLEN=64','-GHAS_H=1','-GHAS_V=1'])
    runtime = {path:sha(ROOT/path) for path in [
        'sw/tests/rv64_hypervisor_basic.S','sw/benchmarks/coremark/rv32_tim.ld',
        'tb/fixtures/bootrom/bootrom_host_jump64.hex']}
    inputs = {**model['inputs'], **runtime, model['binary']:model['binary_sha256']}
    for path,digest in inputs.items():
        assert sha(ROOT/path)==digest,path
    folder = ROOT/'out/rva23/guest_context_restore'
    folder.mkdir(parents=True,exist_ok=True)
    source,elf,trace = (folder/name for name in ['test.S','test.elf','commit.csv'])
    source.write_text(fixture(base.read_text(encoding='utf-8')),encoding='utf-8')
    with Simulator() as sim:
        compile_run,_ = sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh','-mabi=lp64d',
            '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
            '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
        run,text = sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
            '+timeout_cycles=500000','+expected_exit_code=0'],folder/'simulation.log',120)
    assert 'PASS rv32_program_tb' in text and 'data=0x56534354' in text
    with trace.open(newline='') as stream:
        traps = [int(row['cause']) for row in csv.DictReader(stream)
                 if row['trap']=='1' and int(row['pc'],16)>=0x40000000]
    assert traps==[10,10],traps
    for path,digest in inputs.items():
        assert sha(ROOT/path)==digest,path
    dump(folder/'report.json',dict(passed=True,model_sha256=sha(model_path),runtime_inputs=runtime,
         generator_sha256=sha(__file__),compile=compile_run,run=run,traps=traps,
         vector_words=64,fp_words=32,restored_csrs=['vl','vtype','vstart','vcsr','fcsr'],
         artifacts={p.name:sha(p) for p in [source,elf,trace,folder/'simulation.log']}))
    print('PASS HS restore of all VS vector and FP registers and five CSRs')


if __name__=='__main__':
    main()

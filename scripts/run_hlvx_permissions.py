"""Run two-stage HLV/HLVX permission cases on the native RV64 SoC."""
import csv
import json
from itertools import product

from sim_runner import GCC, ROOT, Simulator, dump, sha


FOLDER = 'out/rva23/hlvx_permissions'
BASE = 'sw/tests/rv64_hypervisor_gstage.S'
MARKER = 'data=0x48564c58'


def permission_cases():
    for vs, g, hs_mxr, vs_mxr, op in product('RX', 'RX', (0, 1), (0, 1), ('hlv.d', 'hlvx.wu')):
        if op == 'hlv.d':
            vs_allowed = vs == 'R' or hs_mxr or vs_mxr
            g_allowed = g == 'R' or hs_mxr
        else:
            vs_allowed = vs == 'X'
            g_allowed = g == 'X'
        yield vs, g, hs_mxr, vs_mxr, op, 0, (13 if not vs_allowed else 21 if not g_allowed else 0)
    yield 'X', 'X', 0, 0, 'hlvx.hu', 0, 0
    yield 'X', 'X', 0, 0, 'hlvx.wu', 0x1000, 5
    yield 'X', 'X', 0, 0, 'hlvx.hu', 0x2000, 5


def trap_trace(path):
    with path.open(newline='') as stream:
        return [[int(row['cause']), int(row['tval'], 16)] for row in csv.DictReader(stream)
                if row['trap'] == '1' and int(row['pc'], 16) >= 0x80000000]


def main():
    base = ROOT / BASE
    model_path = ROOT/'out/rva23/hypervisor_integration/model.json'
    model = json.loads(model_path.read_text(encoding='utf-8'))
    assert all(flag in model['params'] for flag in ['-GXLEN=64','-GHAS_H=1','-GHAS_V=1'])
    runtime = {path:sha(ROOT/path) for path in [
        BASE,'sw/benchmarks/coremark/rv32_tim.ld',
        'tb/fixtures/bootrom/bootrom_host_jump64.hex']}
    inputs = {**model['inputs'], **runtime, model['binary']:model['binary_sha256']}
    for path,digest in inputs.items():
        assert sha(ROOT/path)==digest,path
    original = base.read_text(encoding='utf-8')
    code = original.split('hs_entry:\n',1)[0]
    tables = original[original.index('.section .bss'):]
    data = 0x765432108123fe80
    pmp_setup = f'''  li t0,{data:#x}
  li t1,0x800a0000
  sd t0,0(t1)
  li t1,0x800a1000
  sd t0,0(t1)
  li t1,0x800a2000
  sd t0,0(t1)
  li t0,0x200285ff
  csrw pmpaddr0,t0
  li t0,0x200289ff
  csrw pmpaddr1,t0
  li t0,-1
  csrw pmpaddr2,t0
  li t0,0x1f191c
  csrw pmpcfg0,t0
'''
    assert code.count('  mret\n')==1
    code = code.replace('  mret\n',pmp_setup+'  mret\n')
    code += 'hs_entry:\n  li t0,0x100\n  csrw hstatus,t0\n'
    cases = []
    for index, (vs, g, hs_mxr, vs_mxr, op, offset, cause) in enumerate(permission_cases(), 1):
        address = 0x400a0000+offset
        guest_value = (0x200a0000+offset)>>2 if cause==21 else 0
        result = {'hlvx.hu':data&0xffff,'hlvx.wu':data&0xffffffff,'hlv.d':data}[op]
        code += f'''  li s7,{index}
  li t0,0x80000
  csrc sstatus,t0
  csrw vsstatus,zero
'''
        if hs_mxr:
            code += '  csrs sstatus,t0\n'
        if vs_mxr:
            code += '  csrw vsstatus,t0\n'
        code += f'''  la t0,vslevel1
  li t1,{(0x20000000>>2) | (0x49 if vs=='X' else 0x43):#x}
  sd t1,0(t0)
  la t0,glevel1
  li t1,2048
  add t0,t0,t1
  li t1,{(0x80000000>>2) | (0x59 if g=='X' else 0x53):#x}
  sd t1,0(t0)
  hfence.gvma
  hfence.vvma
  li s0,{address:#x}
  li s1,{cause}
  li s2,{guest_value:#x}
  li s3,0
  la s4,probe_{index}
probe_{index}:
  {op} t0,(s0)
  bne s3,s1,fail
'''
        if not cause:
            code += f'  li t1,{result:#x}\n  bne t0,t1,fail\n'
        cases.append(dict(vs=vs, g=g, hs_mxr=hs_mxr, vs_mxr=vs_mxr,
                          op=op, address=address, cause=cause, htval=guest_value))
    code += '''  lui t0,0x10000
  li t1,0x48564c58
  sw t1,0xc(t0)
  sw zero,0x14(t0)
stop:
  j stop
.balign 4
hs_trap:
  beqz s1,fail
  bnez s3,fail
  csrr s3,scause
  bne s3,s1,fail
  csrr t0,sepc
  bne t0,s4,fail
  csrr t1,stval
  bne t1,s0,fail
  csrr t1,htval
  bne t1,s2,fail
  csrr t1,hstatus
  andi t1,t1,0x40
  beqz t1,fail
  addi t0,t0,4
  csrw sepc,t0
  sret
fail:
  lui t0,0x10000
  sw s7,0xc(t0)
  li t1,1
  sw t1,0x14(t0)
  j stop
'''+tables
    folder = ROOT / FOLDER
    folder.mkdir(parents=True,exist_ok=True)
    source,elf,trace = (folder/name for name in ['test.S','test.elf','commit.csv'])
    source.write_text(code,encoding='utf-8')
    with Simulator() as sim:
        compile_run,_ = sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh','-mabi=lp64d',
            '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
            '-T','sw/benchmarks/coremark/rv32_tim.ld',source,'-o',elf],folder/'compile.log',60)
        run,text = sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
            f'+trace_file={trace.relative_to(ROOT).as_posix()}','+quiet_commit',
            '+timeout_cycles=300000','+expected_exit_code=0'],folder/'simulation.log',120)
    assert 'PASS rv32_program_tb' in text and MARKER in text
    traps = trap_trace(trace)
    assert traps == [[case['cause'], case['address']] for case in cases if case['cause']], traps
    for path,digest in inputs.items():
        assert sha(ROOT/path)==digest,path
    dump(folder/'report.json',dict(passed=True,model=model,model_sha256=sha(model_path),runtime_inputs=runtime,
         generator_sha256=sha(__file__),compile=compile_run,run=run,cases=cases,traps=traps,
         source_sha256=sha(source), elf_sha256=sha(elf), trace_sha256=sha(trace)))
    print(f'PASS native HLV/HLVX permissions ({len(cases)} cases, {len(traps)} precise traps)')


if __name__=='__main__':
    main()

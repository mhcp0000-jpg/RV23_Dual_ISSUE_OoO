"""Compare vector FP results and exception flags against the pinned Sail model."""
import concurrent.futures
import json
import os
import subprocess
import sys

from run_sail_event_comparison import compare, read_csv
from sim_runner import GCC, ROOT, Simulator, dump, sha


def fixture(sew):
    if sew == 16:
        a = [0x7c01, 0x7e00, 1, 0x8000, 0x3c00, 0x7bff, 0x7c00, 0xfc00]
        b = [0x7f800001, 0x7f7fffff, 1, 0x3f801000, 0x80000000, 0x7fc00000, 0x3f800000, 0xbf800000]
        ops = [('vfwcvt.f.f.v v8,v16', 16), ('vfncvt.f.f.w v8,v24', 23)]
        vl, lmul, a_size, b_size = 8, 'm1', 2, 4
    else:
        a, b = {
            32: ([0x7f7fffff, 0x3f800000, 0x7f800001, 1],
                 [0x7f7fffff, 0, 0x3f800000, 0x3f000000]),
            64: ([0x7fefffffffffffff, 0x3ff0000000000000, 0x7ff0000000000001, 1],
                 [0x7fefffffffffffff, 0, 0x3ff0000000000000, 0x3fe0000000000000]),
        }[sew]
        ops = [('vfadd.vv v8,v16,v24', 21), ('vfdiv.vv v8,v16,v24', 24),
               ('vfmul.vv v8,v16,v24', 23)]
        vl, lmul, a_size, b_size = 4, 'm1' if sew == 32 else 'm2', sew // 8, sew // 8
    lines = ['.section .text.init,"ax"', '.option norvc', '.option norelax',
             '.globl _start', '_start:', 'la t0,fail', 'csrw mtvec,t0',
             'li t0,0x6600', 'csrw mstatus,t0', f'li t0,{vl}',
             f'vsetvli zero,t0,e{sew},{lmul},tu,mu',
             'la t0,input_a', 'vl2re8.v v16,(t0)', 'la t0,input_b', 'vl2re8.v v24,(t0)']
    expected = []
    for rm in range(5):
        for instruction, flags in ops:
            lines += ['la t0,initial', 'vl2re8.v v8,(t0)', f'csrwi frm,{rm}',
                      'csrw fflags,zero', instruction, 'jal ra,capture']
            expected.append(flags)
    lines += ['la t0,tohost', 'li t1,1', 'sd t1,0(t0)', 'halt:j halt',
              'capture:', 'csrr a3,fflags', 'csrr a4,frm', 'csrr a5,vstart',
              'la t0,snapshot', 'vs2r.v v8,(t0)']
    lines += [f'ld t2,{offset}(t0)' for offset in range(0, 32, 8)]
    lines += ['ret', 'fail:', 'la t0,tohost', 'li t1,3', 'sd t1,0(t0)', 'j halt',
              '.section .tohost,"aw"', '.balign 8', '.globl tohost,fromhost',
              'tohost:.dword 0', 'fromhost:.dword 0', '.section .data,"aw"', '.balign 16']
    for label, values, width in [('input_a',a,a_size), ('input_b',b,b_size), ('initial',[0xa5]*32,1)]:
        data = b''.join(value.to_bytes(width,'little') for value in values).ljust(32,b'\0')
        lines += [label+':', '.byte '+','.join(str(value) for value in data)]
    lines += ['.section .bss,"aw",@nobits', '.balign 32', 'snapshot:.space 32']
    return '\n'.join(lines)+'\n', expected


def main():
    subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'scripts/audit_vector_state_differential.py')],
                   cwd=ROOT, check=True)
    baseline = ROOT/'out/rva23/vector_state_differential/report.json'
    ref_report = ROOT/'out/reference/sail-event-driver/report.json'
    model = json.loads(baseline.read_text(encoding='utf-8'))['model']
    reference = json.loads(ref_report.read_text(encoding='utf-8'))
    config = ROOT/'config/reference/sail-rv23.json'
    folder = ROOT/'out/rva23/vector_fp_differential'
    with Simulator() as sim:
        reference_env = dict(sim.env, PATH='C:/rv_toolchains/cygwin-rv23/bin;'+os.environ['PATH'])

        def one(sew):
            dest = folder/f'e{sew}'
            dest.mkdir(parents=True, exist_ok=True)
            source, elf = dest/'test.S', dest/'test.elf'
            code, expected = fixture(sew)
            source.write_text(code, encoding='utf-8')
            compile_run, _ = sim.run([GCC/'riscv-none-elf-gcc.exe','-march=rv64gcvh_zvfhmin','-mabi=lp64d',
                '-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,--build-id=none',
                '-T','scripts/reference/upstream_htif.ld',source,'-o',elf], dest/'compile.log',60)
            ref_csv, rtl_csv, ref_log = dest/'sail.csv', dest/'rtl.csv', dest/'sail.log'
            with ref_log.open('w',encoding='utf-8') as log:
                subprocess.run([str(ROOT/reference['binary']),'--config',str(config),'--commit-csv',str(ref_csv),
                    '--inst-limit','1000000',str(elf)],cwd=ROOT,env=reference_env,stdout=log,
                    stderr=subprocess.STDOUT,timeout=90,check=True)
            assert 'PASS Sail HTIF' in ref_log.read_text(encoding='utf-8')
            run, output = sim.run([ROOT/model['binary'],f'+elf={elf.relative_to(ROOT).as_posix()}',
                f'+trace_file={rtl_csv.relative_to(ROOT).as_posix()}','+quiet_commit','+htif',
                '+timeout_cycles=3000000','+expected_exit_code=0'],dest/'rtl.log',180)
            assert 'PASS rv32_program_tb' in output
            left, right = read_csv(ref_csv), read_csv(rtl_csv)
            count, mismatch = compare(left,right)
            assert mismatch is None, (sew,mismatch)
            flags = [int(row['wdata'],16) for row in left
                     if int(row['instruction'],16)==0x001026f3]
            assert flags==expected, (sew,flags,expected)
            print(f'PASS vector FP e{sew}: {len(flags)} flag/result checkpoints',flush=True)
            return dict(sew=sew, events=count, flags=flags, compile=compile_run, run=run,
                        artifacts={p.name:sha(p) for p in [source,elf,ref_csv,rtl_csv,ref_log]})

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            cases = list(pool.map(one,[16,32,64]))
    for model_record in [model,reference]:
        assert sha(ROOT/model_record['binary'])==model_record['binary_sha256']
        for path,digest in model_record['inputs'].items():
            assert sha(ROOT/path)==digest
    dump(folder/'report.json',dict(passed=True,baseline_sha256=sha(baseline),
         reference_sha256=sha(ref_report),config_sha256=sha(config),generator_sha256=sha(__file__),
         cases=cases,checkpoints=sum(len(case['flags']) for case in cases)))


if __name__ == '__main__':
    main()

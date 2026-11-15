#!/usr/bin/env python3
"""Build the stock-map RV32 FCVT self-test on Windows or Linux.

This is the local legacy-HostIF test, NOT an HTIF mailbox payload. It needs
the default128KiB TIM map and event/exit0x1000000c/0x10000014. No core options
are set by this builder. Use run_soc_elf_test.ps1 without -Htif for simulation.
"""
import argparse,hashlib,json,os,shutil,struct,subprocess,sys
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()

def load_image_sha(path):
    """Entry/ABI and PT_LOAD bytes/zero-fill shape, not temporary file symbols."""
    data=Path(path).read_bytes()
    h=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
    if h[0][:6]!=b'\x7fELF\x01\x01' or h[2]!=243 or h[9]!=32:
        raise ValueError('Expected little-endian RISC-V ELF32')
    digest=hashlib.sha256(b'RISC-V ELF32 PT_LOAD v1\n'+struct.pack('<II',h[4],h[7]))
    loads=0
    for i in range(h[10]):
        kind,offset,vaddr,paddr,filesz,memsz,flags,align=struct.unpack_from('<IIIIIIII',data,h[5]+i*h[9])
        if kind!=1:continue
        if memsz<filesz or offset+filesz>len(data):raise ValueError('Malformed load segment')
        digest.update(struct.pack('<IIIIII',vaddr,paddr,filesz,memsz,flags,align))
        digest.update(data[offset:offset+filesz]);loads+=1
    if not loads:raise ValueError('No PT_LOAD segments')
    return digest.hexdigest().upper()

def main():
    root=Path(__file__).resolve().parent.parent
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cc',default=shutil.which('riscv-none-elf-gcc') or
                   ('C:/rv_toolchains/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc.exe' if os.name=='nt' else 'riscv-none-elf-gcc'))
    p.add_argument('--output',type=Path,default=Path('out/fp_conversion_vectors'))
    p.add_argument('--checker-negative',action='store_true')
    a=p.parse_args();cc=Path(shutil.which(a.cc) or a.cc).resolve()
    if not cc.is_file():p.error('Compiler not found; pass --cc /path/to/riscv-none-elf-gcc')
    output=(root/a.output).resolve()
    try:relative=output.relative_to(root).as_posix()
    except ValueError:p.error('Output must be inside the repository')
    if output.exists():p.error('Output already exists; choose a new --output to preserve it')
    owned=None;cwd=root
    try:
        # GNU Windows tool argv/temp handling is not reliably Unicode-safe.
        # The alias is scoped to this call and never removes any files.
        if os.name=='nt':
            for letter in 'MNPQRSTUVWXY':
                drive=letter+':'
                if not Path(drive+'/').exists():
                    subprocess.run(['subst',drive,str(root)],check=True,capture_output=True)
                    owned=drive;cwd=Path(drive+'/');break
            if owned is None:raise RuntimeError('No unused temporary drive alias')
        generator='sw/tests/fp_conversion_vectors/gen_vectors.py'
        subprocess.run([sys.executable,generator,'--output',relative],cwd=cwd,check=True)
        sources=['sw/tests/fp_conversion_vectors/start.S','sw/tests/fp_conversion_vectors/test.c']
        linker='sw/tests/rv32_c_loop/rv32_tim.ld'
        args=['-march=rv32imfc_zicsr_zifencei','-mabi=ilp32f','-O2','-std=c11','-ffreestanding',
              '-fno-builtin','-msmall-data-limit=0','-nostdlib','-nostartfiles','-static',
              '-Wl,--build-id=none','-Wl,--no-relax','-Wl,-T,'+linker,'-I'+relative,
              *sources,'-o',relative+'/test.elf']
        if a.checker_negative:args.insert(0,'-DFP_CONVERSION_WRONG_EXPECTED=1')
        with (output/'compile.log').open('w',encoding='utf-8') as stream:
            result=subprocess.run([str(cc),*args],cwd=cwd,stdout=stream,stderr=subprocess.STDOUT)
        report=dict(scope=__doc__,nativeCompileExit=result.returncode,compilerSha256=sha(cc),arguments=args,
                    sources={f:sha(root/f) for f in [generator,linker,*sources]},
                    negativeExpected=a.checker_negative)
        if result.returncode==0:
            report['elfSha256']=sha(output/'test.elf')
            report['loadImageSha256']=load_image_sha(output/'test.elf')
        (output/'build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        if result.returncode:raise RuntimeError('Compile failed; see '+str(output/'compile.log'))
        print('ELF:',output/'test.elf')
        print('Legacy HostIF only; not HTIF.')
        if a.checker_negative:print('Deliberately wrong expectation: eventdeadfc32/exit1 is expected.')
        else:print('Expected conversions14448, success event46504356/exit0.')
        return 0
    finally:
        if owned:subprocess.run(['subst',owned,'/D'],check=True,capture_output=True)

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as e:
        print('FAIL:',e,file=sys.stderr);sys.exit(1)

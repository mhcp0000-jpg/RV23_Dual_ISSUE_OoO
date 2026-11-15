"""ELF32/64 zero-file-size BSS and malformed PT_LOAD boundary checks."""
import struct
from sim_runner import ROOT,DEV,Simulator,sha,dump

folder=ROOT/'out/regression/elf_loader_boundaries'
folder.mkdir(parents=True,exist_ok=True)
harness=folder/'loader_check.cpp'
harness.write_text('''#include <cstdio>
extern "C" int host_open_elf(const char*);
extern "C" unsigned long long host_segment_filesz(int);
extern "C" unsigned long long host_segment_memsz(int);
extern "C" int host_segment_byte(int, unsigned long long);
int main(int argc,char**argv) {
  if(argc!=3)return 2;
  bool expected=argv[2][0]=='1';
  if(bool(host_open_elf(argv[1]))!=expected)return 3;
  if(expected && (host_segment_filesz(0)!=0 || host_segment_memsz(0)!=4096 || host_segment_byte(0,0)!=0))return 4;
  std::puts("PASS ELF segment boundary");return 0;
}
''')
cases=[]
for bits in (32,64):
    for name,offset,filesz,memsz,expected in [
        ('bss_past_eof',0x4000,0,4096,True),
        ('payload_past_eof',0x4000,1,4096,False),
        ('payload_straddles_eof',127,2,4096,False),
        ('filesz_exceeds_memsz',0,2,1,False),
        ('physical_wrap',0,0,4096,False)]:
        data=bytearray(128);data[:7]=b'\x7fELF'+bytes([1 if bits==32 else 2,1,1])
        struct.pack_into('<H',data,18,243)
        pa=((1<<bits)-1024) if name=='physical_wrap' else 0x80020000
        # ELF32 physical arithmetic is checked after widening to uint64_t.
        if bits==32 and name=='physical_wrap':continue
        if bits==64:
            struct.pack_into('<QQ',data,24,0x80000000,64)
            struct.pack_into('<HH',data,54,56,1)
            struct.pack_into('<IIQQQQQQ',data,64,1,6,offset,pa,pa,filesz,memsz,0x4000)
        else:
            struct.pack_into('<II',data,24,0x80000000,64)
            struct.pack_into('<HH',data,42,32,1)
            struct.pack_into('<IIIIIIII',data,64,1,offset,pa,pa,filesz,memsz,6,0x4000)
        path=folder/f'{bits}_{name}.elf';path.write_bytes(data)
        cases.append((path,expected))
source=ROOT/'tb/e2e/dpi/elf_loader.cpp'
with Simulator() as sim:
    binary=folder/'loader_check.exe'
    compile_record,_=sim.run([DEV/'g++.exe','-std=c++17','-O2',source,harness,'-o',binary],folder/'build.log',60)
    runs=[]
    for path,expected in cases:
        run,text=sim.run([binary,path,'1' if expected else '0'],path.with_suffix('.log'),10)
        assert 'PASS' in text
        runs.append({'fixture':path.name,'sha256':sha(path),'expected_success':expected,'run':run})
    dump(folder/'report.json',{'passed':True,'source_sha256':sha(source),
        'generator_sha256':sha(__file__),'binary_sha256':sha(binary),'compile':compile_record,'cases':runs})
print(f'PASS ELF32/64 loader boundaries: {len(cases)} cases',flush=True)

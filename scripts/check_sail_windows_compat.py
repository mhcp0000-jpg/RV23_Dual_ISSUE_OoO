"""Exercise the POSIX line-reader contract required by Sail on native Windows."""
from sim_runner import ROOT,Simulator,DEV,sha,dump

folder=ROOT/'out/reference/windows_compat';folder.mkdir(parents=True,exist_ok=True)
source=folder/'test.c'
source.write_text(r'''
#include "windows_posix_compat.h"
#include <assert.h>
#include <string.h>
int main(void) {
    FILE *stream=tmpfile();assert(stream);
    fputs("\nshort\n",stream);
    for(int i=0;i<4096;i++)fputc('x',stream);
    fputc('\n',stream);fwrite("a\0b\nlast",1,8,stream);rewind(stream);
    char *line=NULL;size_t cap=0;
    assert(getline(&line,&cap,stream)==1 && strcmp(line,"\n")==0);
    assert(getline(&line,&cap,stream)==6 && strcmp(line,"short\n")==0);
    assert(getline(&line,&cap,stream)==4097 && line[4096]=='\n' && line[4097]==0);
    assert(getline(&line,&cap,stream)==4 && memcmp(line,"a\0b\n",4)==0 && line[4]==0);
    assert(getline(&line,&cap,stream)==4 && strcmp(line,"last")==0);
    assert(getline(&line,&cap,stream)==-1 && feof(stream));
    free(line);fclose(stream);
    stream=tmpfile();assert(stream);line=NULL;cap=0;
    assert(getline(&line,&cap,stream)==-1 && feof(stream));
    assert(getline(NULL,&cap,stream)==-1 && errno==EINVAL);
    free(line);fclose(stream);
    puts("PASS Sail Windows getline: empty/short/growing/embedded-NUL/no-newline/EOF/invalid-input");
    return 0;
}
''',encoding='utf-8')
header=ROOT/'scripts/reference/windows_posix_compat.h'
with Simulator() as sim:
    binary=folder/'test.exe'
    compile_record,_=sim.run([DEV/'gcc.exe','-std=c11','-Wall','-Wextra','-Werror',
        '-I'+str(header.parent),source,'-o',binary],folder/'compile.log',30)
    run,text=sim.run([binary],folder/'simulation.log',30)
    assert 'PASS Sail Windows getline' in text
    dump(folder/'report.json',dict(passed=True,scope='Windows legacy text-image line reader compatibility only; no RTL/ISA verdict',
        header_sha256=sha(header),generator_sha256=sha(__file__),source_sha256=sha(source),
        binary_sha256=sha(binary),compile=compile_record,run=run))
print(text.strip(),flush=True)

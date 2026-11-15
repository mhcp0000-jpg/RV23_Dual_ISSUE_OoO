"""Independent official SoftFloat check of the inherited oracle's UF boundary."""
from sim_runner import ROOT,Simulator,DEV,sha,dump
archive=ROOT/'out/imports/SoftFloat-3e.zip'
assert sha(archive)=='21130ce885d35c1fe73fc1e1bf2244178167e05c6747cad5f450cc991714c746'
folder=ROOT/'out/rva23/fp_format';folder.mkdir(parents=True,exist_ok=True)
relative='out/imports/softfloat/SoftFloat-3e'
with Simulator() as sim:
    build=sim.drive+'/'+relative+'/build/Win64-MinGW-w64'
    compile_c='gcc -c -Werror-implicit-function-declaration -DSOFTFLOAT_FAST_INT64 -DSOFTFLOAT_ROUND_ODD -DINLINE_LEVEL=5 -DSOFTFLOAT_FAST_DIV32TO16 -DSOFTFLOAT_FAST_DIV64TO32 -I. -I../../source/8086-SSE -I../../source/include -O2 -o $@'
    build_run,_=sim.run([DEV/'make.exe','-C',build,'-j2','COMPILE_C='+compile_c,'MAKELIB=ar crs $@'],folder/'softfloat_build.log',300)
    exe=folder/'softfloat_tininess.exe'
    compile_run,_=sim.run([DEV/'gcc.exe','-O2','-I'+sim.drive+'/'+relative+'/source/include',
        sim.drive+'/tb/oracles/softfloat_tininess.c',build+'/softfloat.a','-o',exe],folder/'softfloat_driver_compile.log',60)
    run,text=sim.run([exe],folder/'softfloat_tininess.log',30)
    assert 'PASS official SoftFloat' in text
    dump(folder/'tininess_reference.json',{'passed':True,'archive_sha256':sha(archive),
        'driver_sha256':sha(ROOT/'tb/oracles/softfloat_tininess.c'),
        'binary_sha256':sha(exe),'build':build_run,'compile':compile_run,'run':run,
        'finding':'The inherited binary32 oracle omitted UF for some normal-output directed-rounding boundary cases. Active FP64 oracle uses unbounded-exponent tininess.'})
    print(text,flush=True)

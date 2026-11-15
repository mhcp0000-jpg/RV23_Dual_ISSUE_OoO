"""Build the pinned, unmodified official Sail model with an LP64 host ABI."""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from sim_runner import ROOT, Simulator, sha, dump

source = ROOT / 'third_party/sail-riscv'
folder = ROOT / 'out/reference/sail-riscv-0.16-cygwin'
folder.mkdir(parents=True, exist_ok=True)
commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
assert commit == 'e5acebb04ff573e93203596486b831a5974117c3'
assert not subprocess.check_output(['git', '-C', str(source), 'diff', '--name-only'], text=True).strip()
compiler = Path('C:/rv_toolchains/sail-0.20.3/sail/bin/sail.exe')
cygwin = Path('C:/rv_toolchains/cygwin-rv23/bin')
wrapper = ROOT / 'scripts/reference/sail_cygwin.sh'
driver = ROOT / 'scripts/reference/sail_bounded_driver.cpp'
subprocess.run([sys.executable, str(ROOT / 'scripts/check_sail_host_abi.py')], check=True)
report = dict(passed=False, model_commit=commit, model_version='0.16',
              host_abi='Cygwin x86_64 LP64; MinGW LLP64 is not a valid oracle build',
              compiler_sha256=sha(compiler), generator_sha256=sha(__file__),
              wrapper_sha256=sha(wrapper), driver_sha256=sha(driver),
              trace_driver_sha256=sha(ROOT/'scripts/reference/sail_trace_callbacks.h'),
              host_driver='Local bounded ELF/HTIF driver; upstream ISA/model/runtime remain unmodified; no network/GDB CLI',
              scope='Reference-model build only; no RTL verdict')
path = folder / 'build_report.json'
dump(path, report)
with Simulator() as sim:
    # Only this process receives the POSIX tools. No global PATH or profile edits.
    sim.env['PATH'] = str(cygwin) + ';' + str(compiler.parent) + ';' + os.environ['PATH']
    stable_root = Path('C:/rv_workspaces/rv23')
    assert stable_root.resolve() == ROOT.resolve(), 'Stable reference build junction must target this project'
    prefix = '/cygdrive/c/rv_workspaces/rv23'
    build = prefix + '/out/reference/sail-riscv-0.16-cygwin/build'
    src = prefix + '/third_party/sail-riscv'
    posix_wrapper = prefix + '/scripts/reference/sail_cygwin.sh'
    cache = folder / 'build/model/sail_smt_cache'
    old_cache = ROOT / 'out/reference/sail-riscv-0.16/build/model/sail_smt_cache'
    if old_cache.exists() and not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_cache, cache)
    try:
        sim.run([cygwin / 'chmod.exe', '+x', posix_wrapper], folder / 'wrapper.log', 30)
        cache_file = folder/'build/CMakeCache.txt'
        fresh = ['--fresh'] if cache_file.exists() and ('CMAKE_HOME_DIRECTORY:INTERNAL='+src) not in cache_file.read_text(encoding='utf-8') else []
        report['configure'], _ = sim.run([
            cygwin / 'cmake.exe', *fresh, '-S', src, '-B', build, '-G', 'Ninja',
            '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_FLAGS_RELEASE=-O1 -DNDEBUG',
            '-DCMAKE_C_COMPILER=/usr/bin/gcc', '-DCMAKE_CXX_COMPILER=/usr/bin/g++',
            '-DSAIL_BIN=' + posix_wrapper, '-DENABLE_RISCV_TESTS=OFF', '-DFIRST_PARTY_TESTS=OFF'],
            folder / 'configure.log', 300)
        dump(path, report)
        print('CONFIGURED official Sail 0.16 with Cygwin LP64; building reference', flush=True)
        report['build'], _ = sim.run([
            cygwin / 'cmake.exe', '--build', build, '--target', 'riscv_model', '-j2'],
            folder / 'build.log', 3600)
        binary = folder / 'sail_rv23_reference.exe'
        include_paths = [src+'/c_emulator', src+'/dependencies/elfio', build,
            build+'/c_emulator', build+'/config', build+'/_deps/jsoncons-src/include',
            '/cygdrive/c/rv_toolchains/sail-0.20.3/sail/share/sail/lib']
        report['driver_build'], _ = sim.run([cygwin/'g++.exe', '-std=gnu++17', '-O1',
            *['-I'+p for p in include_paths], prefix+'/scripts/reference/sail_bounded_driver.cpp',
            src+'/c_emulator/riscv_callbacks_log.cpp', build+'/c_emulator/libriscv_model.a',
            build+'/dependencies/softfloat/libsoftfloat.a', build+'/sail_runtime/libsail_runtime.a',
            '-lgmp', '-o', prefix+'/'+binary.relative_to(ROOT).as_posix()], folder/'driver_build.log', 180)
        report['version'], output = sim.run([binary, '--version'], folder / 'version.log', 30)
        assert '0.16' in output, output
        report['binary'] = binary.relative_to(ROOT).as_posix()
        report['binary_sha256'] = sha(binary)
        report['host_runtime_sha256'] = {str(p):sha(p) for p in [cygwin/'cygwin1.dll',
            cygwin/'cyggmp-10.dll',cygwin/'cygstdc++-6.dll',cygwin/'gcc.exe',cygwin/'g++.exe']}
        report['host_abi_report_sha256'] = sha(ROOT/'out/reference/host_abi/report.json')
        report['generated_inputs'] = {name: sha(folder / 'build' / name) for name in (
            'sail_riscv_model.cpp', 'sail_riscv_model.h', 'sail_riscv_config_schema.json')}
        report['passed'] = True
    finally:
        dump(path, report)
print('PASS official Sail reference executable', report['binary'], flush=True)

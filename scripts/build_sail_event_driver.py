"""Link a separate event-complete trace host against the existing Sail model."""
import json
import os

from sim_runner import ROOT, Simulator, dump, sha


def main():
    base = ROOT / 'out/reference/sail-riscv-0.16-cygwin/build_report.json'
    report = json.loads(base.read_text(encoding='utf-8'))
    assert report['passed'] and sha(ROOT / report['binary']) == report['binary_sha256']
    for key, path in [('driver_sha256', 'scripts/reference/sail_bounded_driver.cpp'),
                      ('trace_driver_sha256', 'scripts/reference/sail_trace_callbacks.h')]:
        assert sha(ROOT / path) == report[key]
    folder = ROOT / 'out/reference/sail-event-driver'
    folder.mkdir(parents=True, exist_ok=True)
    driver = folder / 'sail_bounded_driver.cpp'
    contents = (ROOT / 'scripts/reference/sail_bounded_driver.cpp').read_text(encoding='utf-8')
    anchor = '#include "sail_trace_callbacks.h"'
    assert contents.count(anchor) == 1
    driver.write_text(contents.replace(anchor, '#include "sail_trace_events.h"'), encoding='utf-8')
    prefix = '/cygdrive/c/rv_workspaces/rv23'
    src = prefix + '/third_party/sail-riscv'
    build = prefix + '/out/reference/sail-riscv-0.16-cygwin/build'
    libs = ['out/reference/sail-riscv-0.16-cygwin/build/' + path for path in [
        'c_emulator/libriscv_model.a', 'dependencies/softfloat/libsoftfloat.a', 'sail_runtime/libsail_runtime.a']]
    inputs = {path:sha(ROOT / path) for path in libs + [
        'scripts/reference/sail_trace_events.h', 'scripts/reference/sail_bounded_driver.cpp',
        'third_party/sail-riscv/c_emulator/riscv_callbacks_log.cpp']}
    binary = folder / 'sail_rv23_events.exe'
    with Simulator() as sim:
        sim.env['PATH'] = 'C:/rv_toolchains/cygwin-rv23/bin;' + os.environ['PATH']
        includes = [src + '/c_emulator', src + '/dependencies/elfio', build,
                    build + '/c_emulator', build + '/config', build + '/_deps/jsoncons-src/include',
                    prefix + '/scripts/reference', '/cygdrive/c/rv_toolchains/sail-0.20.3/sail/share/sail/lib']
        compile_run, _ = sim.run(['C:/rv_toolchains/cygwin-rv23/bin/g++.exe', '-std=gnu++17', '-O1',
            *['-I' + path for path in includes], prefix + '/' + driver.relative_to(ROOT).as_posix(),
            src + '/c_emulator/riscv_callbacks_log.cpp', *[prefix + '/' + path for path in libs],
            '-lgmp', '-o', prefix + '/' + binary.relative_to(ROOT).as_posix()], folder / 'build.log', 180)
        version, text = sim.run([binary, '--version'], folder / 'version.log', 30)
        assert 'Sail RISC-V 0.16' in text
    for path, digest in inputs.items():
        assert sha(ROOT / path) == digest
    assert sha(ROOT / report['binary']) == report['binary_sha256']
    dump(folder / 'report.json', dict(passed=True, scope='Separate trace host; same unmodified Sail model libraries',
        generator_sha256=sha(__file__), base_report_sha256=sha(base), inputs=inputs,
        generated_driver_sha256=sha(driver), binary=binary.relative_to(ROOT).as_posix(),
        binary_sha256=sha(binary), compile=compile_run, version=version))
    print('PASS separate Sail event trace driver', flush=True)


if __name__ == '__main__':
    main()

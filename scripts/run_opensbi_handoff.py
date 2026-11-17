"""Boot an S-mode probe or a Linux Image through upstream OpenSBI."""

import argparse
import json
import re
import subprocess
import sys

from audit_linux_boot import verify_boot_log, verify_firmware_payload, verify_vector_initramfs
from sim_runner import GCC, ROOT, Simulator, dump, sha, source_inputs


MSYS = 'C:/rv_toolchains/msys-act4/msys64'
WORKSPACE = 'C:/rv_workspaces/rv23'
OPEN_SBI_COMMIT = 'a32a91069119e7a5aa31e6bc51d5e00860be3d80'
LINUX_SUPM_ARCHIVE = 'out/linux_bringup/downloads/linux-6.14.tar.xz'
LINUX_SUPM_ARCHIVE_SHA256 = 'a294b683e7b161bb0517bb32ec7ed1d2ea7603dfbabad135170ed12d00c47670'


def save_report(path, report):
    pending = path.with_suffix('.json.tmp')
    dump(pending, report)
    pending.replace(path)


def run_linux(sim, folder, report, timeout):
    model = report['boot_model']
    elf = report['elf']
    report['run'], log = sim.run(
        [ROOT / model['binary'], f'+elf={elf}', '+quiet_commit', '+htif',
         '+linux_watch', '+timeout_cycles=100000000', '+elf_verify=0'],
        folder / 'rtl.log', timeout)
    report['boot_witnesses'] = verify_boot_log(
        log, vector=report.get('linux_vector', False), supm=report.get('linux_supm', False))
    model['passed'] = True
    report['passed'] = True
    print('PASS Linux boot, initramfs /init and SBI power-off', flush=True)


def reuse_linux_build(report_path, folder, image, base_model_hash):
    report = json.loads(report_path.read_text(encoding='utf-8'))
    assert not report['passed'] and report['opensbi_commit'] == OPEN_SBI_COMMIT
    model = report['boot_model']
    assert model['sram_kib'] == 32768
    assert report['model_sha256'] == model['base_model_sha256'] == base_model_hash
    assert sha(image) == report['linux_image_sha256']
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    elf = ROOT / report['elf']
    assert sha(elf) == model['firmware_sha256'] == report['elf_sha256']
    for inputs in (report['inputs'], model['inputs'], model['overridden_sources']):
        for path, digest in inputs.items():
            assert sha(ROOT / path) == digest, path
    verify_firmware_payload(elf.read_bytes(), image.read_bytes(), (folder / 'rv23.dtb').read_bytes())
    report.pop('run', None)
    return report


def reuse_linux_firmware(folder, image, variant, vector, supm):
    source = ROOT / 'out/linux_bringup' / variant / 'firmware'
    previous = json.loads((source / 'report.json').read_bytes())
    assert previous['opensbi_commit'] == OPEN_SBI_COMMIT and previous.get('linux_vector', False) == vector
    assert previous.get('linux_supm', False) == supm
    assert sha(image) == previous['linux_image_sha256']
    firmware = ROOT / previous['elf']
    assert sha(firmware) == previous['elf_sha256']
    for path, digest in previous['inputs'].items():
        assert sha(ROOT / path) == digest, path
    dtb = (source / 'rv23.dtb').read_bytes()
    verify_firmware_payload(firmware.read_bytes(), image.read_bytes(), dtb)
    (folder / 'rv23.dtb').write_bytes(dtb)
    inherited = ('elf', 'elf_sha256', 'inputs', 'linux_image', 'linux_image_sha256', 'linux_vector',
                 'linux_vector_init', 'linux_vector_initramfs', 'linux_supm')
    return {key: previous[key] for key in inherited if key in previous}


def boot_linux_case(sim, folder, report, report_path, args):
    variant_args = ['--variant', args.variant] if args.variant else []
    sim.run([sys.executable, '-X', 'utf8', 'scripts/build_linux_sim_model.py', report['elf'], *variant_args],
            folder / 'linux-model-build.log', 1500)
    report['boot_model'] = json.loads((folder.parent / 'rtl/model.json').read_bytes())
    save_report(report_path, report)
    run_linux(sim, folder, report, args.boot_timeout)


def boot_probe(sim, output, report, base):
    folder = ROOT / output
    elf = report['elf']
    symbols = subprocess.check_output([f'{MSYS}/ucrt64/bin/llvm-nm.exe', f'{WORKSPACE}/{elf}'], text=True)
    mailboxes = {fields[-1]: int(fields[0], 16) for line in symbols.splitlines()
                 if len(fields := line.split()) == 3 and fields[-1] in ('tohost', 'fromhost')}
    assert set(mailboxes) == {'tohost', 'fromhost'} and len(set(mailboxes.values())) == 2
    assert all(0x80020000 <= address <= 0x800ffff8 and address % 8 == 0 for address in mailboxes.values())
    template = (ROOT / 'tb/e2e/rv_act4_program_tb.sv').read_text(encoding='utf-8')
    marker = 'rv_host_dpi #(.HTIF_ENABLE(1),'
    assert template.count(marker) == 1
    ports = ''.join(f".{name.upper()}_ADDR(32'h{address:08x})," for name, address in mailboxes.items())
    boot_tb = f'{output}/rv_act4_program_tb.sv'
    (ROOT / boot_tb).write_text(template.replace(marker, marker + ports), encoding='utf-8')
    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
        'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
        boot_tb, 'tb/e2e/dpi/elf_loader.cpp']
    model = sim.build('opensbi_handoff_htif', base['top'], files, base['params'])
    report['boot_model'] = model
    report['mailboxes'] = mailboxes
    report['run'], log = sim.run([ROOT / model['binary'], f'+elf={elf}', '+quiet_commit', '+htif',
                                 '+timeout_cycles=6000000', '+elf_verify=0',
                                 f'+trace_file={output}/retire.csv'], folder / 'rtl.log', 900)
    assert 'OPENSBI S-MODE DTB AND TIMER PASS' in log and 'PASS rv_act4_program_tb' in log, log[-1500:]
    assert sha(ROOT / elf) == report['elf_sha256'] and model['inputs'] == source_inputs(files)
    model['passed'] = True
    report['passed'] = True
    print('PASS OpenSBI handoff, SBI BASE/TIME, and supervisor timer interrupt', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--linux-image', help='RV64 Linux Image with built-in initramfs')
    parser.add_argument('--variant', help='Preserve earlier results in a separate named Linux run')
    parser.add_argument('--linux-vector', action='store_true',
                        help='Advertise V in the DTB and require vector /init output')
    parser.add_argument('--linux-supm', action='store_true',
                        help='Advertise Ssnpm and require the Linux 6.14 Supm /init probe')
    parser.add_argument('--reuse-build', action='store_true',
                        help='Rerun a failed Linux simulation with its verified existing firmware and model')
    parser.add_argument('--reuse-firmware-from', help='Build a fresh RTL model and replay the exact firmware from this Linux variant')
    parser.add_argument('--reuse-probe-firmware', action='store_true',
                        help='Replay the saved 1 MiB S-mode probe ELF on a fresh RTL model')
    parser.add_argument('--boot-timeout', type=int, default=7200,
                        help='Host timeout in seconds for Linux simulation before any environment scaling')
    args = parser.parse_args()
    linux = args.linux_image is not None
    if args.reuse_build and not linux:
        parser.error('--reuse-build requires --linux-image')
    if args.reuse_probe_firmware and linux:
        parser.error('--reuse-probe-firmware applies to the 1 MiB probe')
    if args.reuse_firmware_from and (not linux or not args.variant or args.variant == args.reuse_firmware_from
                                    or args.reuse_build or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', args.reuse_firmware_from)):
        parser.error('--reuse-firmware-from requires --linux-image and a different --variant')
    if args.linux_vector and (not linux or not args.variant):
        parser.error('--linux-vector requires --linux-image and a separate --variant')
    if args.linux_supm and not args.linux_vector:
        parser.error('--linux-supm requires --linux-vector')
    if args.boot_timeout <= 0:
        parser.error('--boot-timeout must be positive')
    if args.variant:
        assert linux and re.fullmatch(r'[a-z][a-z0-9_]{0,31}', args.variant), 'Invalid Linux variant'
    vendor = ROOT / 'third_party/opensbi'
    commit = subprocess.check_output(['git', '-C', str(vendor), 'rev-parse', 'HEAD'], text=True).strip()
    assert commit == OPEN_SBI_COMMIT
    assert not subprocess.check_output(['git', '-C', str(vendor), 'status', '--porcelain'], text=True).strip()

    fixture = 'tb/fixtures/opensbi'
    output = 'out/linux_bringup/firmware' if linux else 'out/opensbi_handoff_htif'
    if args.variant:
        output = f'out/linux_bringup/{args.variant}/firmware'
    folder = ROOT / output
    folder.mkdir(parents=True, exist_ok=True)
    model_path = ROOT / 'out/act4/dut/model.json'
    model = json.loads(model_path.read_text(encoding='utf-8'))
    assert model['passed'] and sha(ROOT / model['binary']) == model['binary_sha256']
    for name, digest in model['inputs'].items():
        assert sha(ROOT / name) == digest, name

    report_path = folder / 'report.json'
    if args.reuse_build:
        image = (ROOT / args.linux_image).resolve(strict=True)
        report = reuse_linux_build(report_path, folder, image, sha(model_path))
        assert args.linux_vector == report.get('linux_vector', False)
        assert args.linux_supm == report.get('linux_supm', False)
        try:
            with Simulator() as sim:
                run_linux(sim, folder, report, args.boot_timeout)
        finally:
            save_report(report_path, report)
        return

    report = {
        'passed': False,
        'scope': ('Linux boot through OpenSBI with 32 MiB simulated SRAM' if linux else
                  'OpenSBI M-mode firmware to an S-mode ABI and timer probe'),
        'opensbi_commit': commit,
        'model_sha256': sha(model_path),
        'inputs': {name: sha(ROOT / name) for name in (f'{fixture}/rv23.dts', f'{fixture}/smode_probe.S')},
    }
    if args.reuse_probe_firmware:
        previous = json.loads(report_path.read_bytes())
        assert previous['opensbi_commit'] == commit and previous['inputs'] == report['inputs']
        assert sha(ROOT / previous['elf']) == previous['elf_sha256']
        report.update({key: previous[key] for key in ('elf', 'elf_sha256', 'build')})
    try:
        with Simulator() as sim:
            if args.reuse_probe_firmware:
                boot_probe(sim, output, report, model)
                return
            if args.reuse_firmware_from:
                image = (ROOT / args.linux_image).resolve(strict=True)
                report.update(reuse_linux_firmware(folder, image, args.reuse_firmware_from,
                                                   args.linux_vector, args.linux_supm))
                boot_linux_case(sim, folder, report, report_path, args)
                return
            dts = f'{fixture}/rv23.dts'
            if linux:
                image = (ROOT / args.linux_image).resolve(strict=True)
                header = image.open('rb')
                with header:
                    assert header.read(64)[56:60] == b'RSC\x05', 'Expected RISC-V Linux Image'
                assert image.stat().st_size < 30 * 1024 * 1024
                payload = folder / 'probe.bin'
                payload.write_bytes(image.read_bytes())
                report['linux_image'] = payload.relative_to(ROOT).as_posix()
                report['linux_image_sha256'] = sha(payload)
                text = (ROOT / dts).read_text(encoding='utf-8')
                text = text.replace('0 0x100000>;', '0 0x2000000>;')
                text = text.replace('stdout-path = "/htif";',
                                    'stdout-path = "/htif";\n        bootargs = "earlycon=sbi keep_bootcon";')
                isa = 'riscv,isa = "rv64imafdc_zicsr_zifencei_zicntr_sstc";'
                assert text.count(isa) == 1
                vector_isa = isa.replace('imafdc_', 'imafdcv_') if args.linux_vector else isa
                vector_extension = ' "v",' if args.linux_vector else ''
                supm_extension = ', "ssnpm"' if args.linux_supm else ''
                if args.linux_supm:
                    vector_isa = vector_isa.replace('_sstc"', '_sstc_ssnpm"')
                text = text.replace(isa, vector_isa + '\n            riscv,isa-base = "rv64i";'
                                    '\n            riscv,isa-extensions = "i", "m", "a", "f", "d", "c",' + vector_extension +
                                    '\n                                   "zicsr", "zifencei", "zicntr", "sstc"' +
                                    supm_extension + ';')
                if args.linux_vector:
                    kbuild = image.parents[3]
                    init = kbuild.parent / 'init.elf'
                    config = kbuild / '.config'
                    initramfs = kbuild / 'usr/initramfs_inc_data'
                    config_flags = {'CONFIG_RISCV_ISA_V=y', 'CONFIG_FPU=y', 'CONFIG_INITRAMFS_COMPRESSION_GZIP=y'}
                    fixture_inputs = [ROOT / fixture / 'linux_init.S']
                    if args.linux_supm:
                        config_flags.add('CONFIG_RISCV_ISA_SUPM=y')
                        fixture_inputs.extend((ROOT / fixture / 'linux_supm_init.S',
                                               ROOT / 'scripts/build_linux_supm_msys.sh'))
                        assert sha(ROOT / LINUX_SUPM_ARCHIVE) == LINUX_SUPM_ARCHIVE_SHA256
                        report['inputs'][LINUX_SUPM_ARCHIVE] = LINUX_SUPM_ARCHIVE_SHA256
                        report['linux_supm'] = True
                    else:
                        fixture_inputs.append(ROOT / 'scripts/build_linux_image_msys.sh')
                    assert config_flags <= set(config.read_text(encoding='utf-8').splitlines())
                    verify_vector_initramfs(payload.read_bytes(), initramfs.read_bytes(), init.read_bytes())
                    report['linux_vector'] = True
                    report['linux_vector_init'] = init.relative_to(ROOT).as_posix()
                    report['linux_vector_initramfs'] = initramfs.relative_to(ROOT).as_posix()
                    for path in (init, initramfs, config, *fixture_inputs):
                        report['inputs'][path.relative_to(ROOT).as_posix()] = sha(path)
                dts = f'{output}/linux.dts'
                (ROOT / dts).write_text(text, encoding='utf-8')
                report['inputs'][dts] = sha(ROOT / dts)
            sim.run([f'{MSYS}/ucrt64/bin/dtc.exe', '-I', 'dts', '-O', 'dtb',
                     '-o', f'{WORKSPACE}/{output}/rv23.dtb', f'{WORKSPACE}/{dts}'],
                    folder / 'dtc.log', 60)
            if not linux:
                sim.run([GCC / 'riscv-none-elf-gcc.exe', '-march=rv64i_zicsr_zicntr', '-mabi=lp64',
                         '-nostdlib', '-Wl,-Ttext=0x80080000', '-o', f'{WORKSPACE}/{output}/probe.elf',
                         f'{WORKSPACE}/{fixture}/smode_probe.S'], folder / 'probe-build.log', 60)
                sim.run([GCC / 'riscv-none-elf-objcopy.exe', '-O', 'binary', '-j', '.text',
                         f'{WORKSPACE}/{output}/probe.elf', f'{WORKSPACE}/{output}/probe.bin'],
                        folder / 'probe-objcopy.log', 60)

            sim.env['MSYSTEM'] = 'UCRT64'
            build_command = (
                'printf "void _start(void) {}\\n" | clang --target=riscv64-unknown-elf '
                '-mno-relax -fuse-ld=lld -fPIE -nostdlib -Wl,-pie -x c - '
                '-o /c/rv_workspaces/rv23/out/opensbi_handoff/pie-test.elf && '
                'cd /c/rv_workspaces/rv23/third_party/opensbi && '
                'make -j4 O=/c/rv_workspaces/rv23/out/opensbi_handoff/build PLATFORM=generic LLVM=1 '
                'OPENSBI_LD_PIE=y '
                'REPRODUCIBLE=y '
                'FW_DYNAMIC=n FW_JUMP=n FW_PAYLOAD=y FW_TEXT_START=0x80000000 '
                f'FW_PAYLOAD_OFFSET={"0x200000" if linux else "0x80000"} '
                f'FW_PAYLOAD_FDT_OFFSET={"0x100000" if linux else "0x90000"} FW_FDT_PADDING=4096 '
                'FW_FDT_PATH=../../out/opensbi_handoff/rv23.dtb '
                'FW_PAYLOAD_PATH=../../out/opensbi_handoff/probe.bin'
            )
            build_command = build_command.replace('out/opensbi_handoff', output)
            report['build'], _ = sim.run([f'{MSYS}/usr/bin/bash.exe', '-lc', build_command],
                                         folder / 'opensbi-build.log', 900)
            elf = f'{output}/build/platform/generic/firmware/fw_payload.elf'
            report['elf'] = elf
            report['elf_sha256'] = sha(ROOT / elf)
            if linux:
                boot_linux_case(sim, folder, report, report_path, args)
                return
            boot_probe(sim, output, report, model)
    finally:
        save_report(report_path, report)


if __name__ == '__main__':
    main()

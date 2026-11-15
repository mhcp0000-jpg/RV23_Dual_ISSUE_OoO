"""Boot an S-mode probe or a Linux Image through upstream OpenSBI."""

import argparse
import json
import re
import subprocess
import sys

from audit_linux_boot import verify_boot_log, verify_firmware_payload
from sim_runner import GCC, ROOT, Simulator, dump, sha


MSYS = 'C:/rv_toolchains/msys-act4/msys64'
WORKSPACE = 'C:/rv_workspaces/rv23'
OPEN_SBI_COMMIT = 'a32a91069119e7a5aa31e6bc51d5e00860be3d80'


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
    report['boot_witnesses'] = verify_boot_log(log)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--linux-image', help='RV64 Linux Image with built-in initramfs')
    parser.add_argument('--variant', help='Preserve earlier results in a separate named Linux run')
    parser.add_argument('--reuse-build', action='store_true',
                        help='Rerun a failed Linux simulation with its verified existing firmware and model')
    parser.add_argument('--boot-timeout', type=int, default=7200,
                        help='Host timeout in seconds for Linux simulation before any environment scaling')
    args = parser.parse_args()
    linux = args.linux_image is not None
    if args.reuse_build and not linux:
        parser.error('--reuse-build requires --linux-image')
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
    try:
        with Simulator() as sim:
            dts = f'{fixture}/rv23.dts'
            if linux:
                image = (ROOT / args.linux_image).resolve(strict=True)
                header = image.open('rb')
                with header:
                    assert header.read(64)[56:60] == b'RSC\x05', 'Expected RISC-V Linux Image'
                assert image.stat().st_size < 30 * 1024 * 1024
                payload = folder / 'probe.bin'
                payload.write_bytes(image.read_bytes())
                report['linux_image_sha256'] = sha(payload)
                text = (ROOT / dts).read_text(encoding='utf-8')
                text = text.replace('0 0x100000>;', '0 0x2000000>;')
                text = text.replace('stdout-path = "/htif";',
                                    'stdout-path = "/htif";\n        bootargs = "earlycon=sbi keep_bootcon";')
                isa = 'riscv,isa = "rv64imafdc_zicsr_zifencei_zicntr_sstc";'
                assert text.count(isa) == 1
                text = text.replace(isa, isa + '\n            riscv,isa-base = "rv64i";'
                                    '\n            riscv,isa-extensions = "i", "m", "a", "f", "d", "c",'
                                    '\n                                   "zicsr", "zifencei", "zicntr", "sstc";')
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
                variant_args = ['--variant', args.variant] if args.variant else []
                sim.run([sys.executable, '-X', 'utf8', 'scripts/build_linux_sim_model.py', elf, *variant_args],
                        folder / 'linux-model-build.log', 1500)
                model_folder = folder.parent / 'rtl'
                boot_model = json.loads((model_folder / 'model.json').read_text(encoding='utf-8'))
                report['boot_model'] = boot_model
                save_report(report_path, report)
                run_linux(sim, folder, report, args.boot_timeout)
                return
            symbols = subprocess.check_output([f'{MSYS}/ucrt64/bin/llvm-nm.exe',
                                                f'{WORKSPACE}/{elf}'], text=True)
            mailboxes = {fields[-1]: int(fields[0], 16) for line in symbols.splitlines()
                         if len(fields := line.split()) == 3 and fields[-1] in ('tohost', 'fromhost')}
            assert len(mailboxes) == 2 and len(set(mailboxes.values())) == 2
            for address in mailboxes.values():
                assert 0x80020000 <= address <= 0x800ffff8 and address % 8 == 0
            original_tb = 'tb/e2e/rv_act4_program_tb.sv'
            template = (ROOT / original_tb).read_text(encoding='utf-8')
            marker = 'rv_host_dpi #(.HTIF_ENABLE(1),'
            assert template.count(marker) == 1
            port_parameters = ''.join(f".{name.upper()}_ADDR(32'h{address:08x}),"
                                      for name, address in mailboxes.items())
            boot_tb = f'{output}/rv_act4_program_tb.sv'
            (ROOT / boot_tb).write_text(template.replace(marker, marker + port_parameters), encoding='utf-8')
            files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines() + [
                'tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
                boot_tb, 'tb/e2e/dpi/elf_loader.cpp']
            boot_model = sim.build('opensbi_handoff_htif', model['top'], files, model['params'])
            report['boot_model'] = boot_model
            report['mailboxes'] = mailboxes
            report['run'], log = sim.run([ROOT / boot_model['binary'], f'+elf={elf}', '+quiet_commit', '+htif',
                                         '+timeout_cycles=6000000', '+elf_verify=0',
                                         f'+trace_file={output}/retire.csv'], folder / 'rtl.log', 900)
            assert 'OPENSBI S-MODE DTB AND TIMER PASS' in log, log[-1500:]
            assert 'PASS rv_act4_program_tb' in log
            boot_model['passed'] = True
            report['passed'] = True
    finally:
        save_report(report_path, report)
    print('PASS OpenSBI handoff, SBI BASE/TIME, and supervisor timer interrupt', flush=True)


if __name__ == '__main__':
    main()

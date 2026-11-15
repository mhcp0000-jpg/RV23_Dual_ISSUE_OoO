"""Verify the current Linux RTL boot against its firmware, model and log."""

import argparse
import hashlib
import json
import re
import struct

from sim_runner import ROOT, dump, sha


def verify_boot_log(log):
    markers = ('LINUX_RTL_S_ENTRY pc=0000000080200000', 'Linux version ',
               'LINUX_RTL_U_RETIRE pc=', 'RV23 LINUX INIT PASS', 'reboot: Power down',
               '[host-finish code=0]', 'PASS rv_act4_program_tb commits=')
    positions = [log.find(marker) for marker in markers]
    assert all(position >= 0 for position in positions) and positions == sorted(positions), log[-3000:]
    return [log[position:].splitlines()[0] for position in positions]


def verify_firmware_payload(firmware, image, dtb):
    assert firmware[:6] == b'\x7fELF\x02\x01' and image[56:60] == b'RSC\x05'
    magic, total_size = struct.unpack_from('>II', dtb)
    assert magic == 0xd00dfeed and total_size == len(dtb)
    entry, phoff = struct.unpack_from('<QQ', firmware, 24)
    phsize, count = struct.unpack_from('<HH', firmware, 54)
    assert entry == 0x80000000
    assert phsize == struct.calcsize('<IIQQQQQQ') and phoff + count * phsize <= len(firmware)

    payload = None
    dtb_addresses = []
    load_image = hashlib.sha256(struct.pack('<Q', entry))
    for index in range(count):
        kind, flags, offset, _, address, size, mem_size, alignment = struct.unpack_from(
            '<IIQQQQQQ', firmware, phoff + index * phsize)
        if kind != 1:
            continue
        assert size <= mem_size and offset + size <= len(firmware)
        assert 0x80000000 <= address and address + mem_size <= 0x82000000
        contents = firmware[offset:offset + size]
        load_image.update(struct.pack('<IQQQQ', flags, address, size, mem_size, alignment))
        load_image.update(contents)
        if address == 0x80200000:
            assert payload is None
            payload = contents
        dtb_offset = firmware.find(dtb, offset, offset + size)
        if dtb_offset >= 0:
            dtb_addresses.append(address + dtb_offset - offset)
    assert payload == image, 'OpenSBI ELF Linux payload differs from Image'
    assert len(dtb_addresses) == 1, 'Expected DTB bytes missing from a unique loadable segment'
    return dtb_addresses[0], load_image.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', help='Audit a separately named Linux run')
    parser.add_argument('--require-isa', action='store_true', help='Require Linux to detect I/M/A/C from the DTB')
    args = parser.parse_args()
    folder = ROOT / 'out/linux_bringup'
    if args.variant:
        assert re.fullmatch(r'[a-z][a-z0-9_]{0,31}', args.variant)
        folder /= args.variant
    path = folder / 'firmware/report.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    run = report['run']
    model = report['boot_model']
    assert report['passed'] and run['passed'] and run['exit_code'] == 0 and model['passed']

    base_model = ROOT / 'out/act4/dut/model.json'
    assert sha(base_model) == model['base_model_sha256'] == report['model_sha256']
    assert model['sram_kib'] == 32768
    for inputs in (report['inputs'], model['inputs'], model['overridden_sources']):
        for name, digest in inputs.items():
            assert sha(ROOT / name) == digest, name
    assert sha(ROOT / model['binary']) == model['binary_sha256']
    assert sha(ROOT / report['elf']) == report['elf_sha256'] == model['firmware_sha256']
    assert sha(ROOT / run['log']) == run['log_sha256']

    image_path = ROOT / 'out/linux_bringup/kbuild-native/arch/riscv/boot/Image'
    assert sha(image_path) == report['linux_image_sha256']
    dtb_path = folder / 'firmware/rv23.dtb'
    dtb_address, load_image_sha256 = verify_firmware_payload(
        (ROOT / report['elf']).read_bytes(), image_path.read_bytes(), dtb_path.read_bytes())

    log = (ROOT / run['log']).read_text(encoding='utf-8', errors='replace')
    witnesses = verify_boot_log(log)
    assert witnesses[1].startswith('Linux version 6.12')
    isa = re.search(r'riscv: base ISA extensions ([a-z]+)', log)
    hwcap = re.search(r'riscv: ELF capabilities ([a-z]+)', log)
    if args.require_isa:
        assert isa and set('imac') <= set(isa.group(1)), 'Linux base ISA detection missing'
        assert hwcap and set('imac') <= set(hwcap.group(1)), 'Linux ELF HWCAP detection missing'
    dump(folder / 'boot_audit.json', {
        'passed': True,
        'report_sha256': sha(path),
        'linux_image_sha256': report['linux_image_sha256'],
        'firmware_sha256': report['elf_sha256'],
        'firmware_load_image_sha256': load_image_sha256,
        'dtb_sha256': sha(dtb_path),
        'embedded_dtb_load_address': hex(dtb_address),
        'model_binary_sha256': model['binary_sha256'],
        'sram_kib': model['sram_kib'],
        'detected_base_isa': isa.group(1) if isa else '',
        'detected_elf_hwcap': hwcap.group(1) if hwcap else '',
        'isa_detection_required': args.require_isa,
        'witnesses': witnesses,
    })
    print('PASS current RTL Linux boot audit', *witnesses, sep='\n')


if __name__ == '__main__':
    main()

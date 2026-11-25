"""Build the existing RV64 SoC with a larger simulated SRAM for Linux."""

import argparse
import json
import re
import subprocess

from sim_runner import ROOT, Simulator, dump, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', help='OpenSBI ELF with the Linux payload and HTIF symbols')
    parser.add_argument('--diagnostic', action='store_true', help='Keep the instrumented build separate from an active boot')
    parser.add_argument('--variant', help='Separate named build and generated-source directory')
    args = parser.parse_args()
    if args.variant:
        assert re.fullmatch(r'[a-z][a-z0-9_]{0,31}', args.variant), 'Invalid variant name'
    firmware = (ROOT / args.firmware).resolve(strict=True)
    base = ROOT / 'out/linux_bringup'
    if args.variant:
        base /= args.variant
    folder = base / ('rtl_diagnostic' if args.diagnostic else 'rtl')
    folder.mkdir(parents=True, exist_ok=True)
    model_path = ROOT / 'out/act4/dut/model.json'
    model = json.loads(model_path.read_text(encoding='utf-8'))
    assert model['passed'] and sha(ROOT / model['binary']) == model['binary_sha256']
    for name, digest in model['inputs'].items():
        assert sha(ROOT / name) == digest, name

    nm = 'C:/rv_toolchains/msys-act4/msys64/ucrt64/bin/llvm-nm.exe'
    symbols = subprocess.check_output([nm, str(firmware)], text=True)
    mailboxes = {}
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[-1] in ('tohost', 'fromhost'):
            mailboxes[fields[-1]] = int(fields[0], 16)
    assert set(mailboxes) == {'tohost', 'fromhost'} and len(set(mailboxes.values())) == 2
    assert all(0x80020000 <= address <= 0x81fffff8 and address % 8 == 0
               for address in mailboxes.values())

    files = (ROOT / 'rtl/filelist.f').read_text(encoding='utf-8').splitlines()
    overrides = {'rtl/soc/rv23_pkg.sv': ('SRAM_KB = 1024;', 'SRAM_KB = 32768;')}
    for stem in ('atomic_head', 'cbo_head', 'hypervisor_memory_head', 'memory_head', 'misaligned_head'):
        overrides[f'rtl/backend/rv23_{stem}.sv'] = ("32'h80100000", "32'h82000000")
    overrides['rtl/soc/rv23_ptw_arbiter.sv'] = ("56'h80100000", "56'h82000000")
    originals = {}
    for name, (old, new) in overrides.items():
        original = ROOT / name
        originals[name] = sha(original)
        contents = original.read_text(encoding='utf-8')
        assert contents.count(old) == 1, name
        generated = folder / original.name
        generated.write_text(contents.replace(old, new), encoding='utf-8')
        files[files.index(name)] = generated.relative_to(ROOT).as_posix()

    tb_source = 'tb/e2e/rv_act4_program_tb.sv'
    originals[tb_source] = sha(ROOT / tb_source)
    template = (ROOT / tb_source).read_text(encoding='utf-8')
    marker = 'rv_host_dpi #(.HTIF_ENABLE(1),'
    assert template.count(marker) == 1
    ports = ''.join(f".{name.upper()}_ADDR(32'h{address:08x})," for name, address in mailboxes.items())
    for old, new in [('ITIM_SIZE_BYTES(1024*1024)', 'ITIM_SIZE_BYTES(32*1024*1024)'),
                     ('DTIM_SIZE_BYTES(896*1024)', 'DTIM_SIZE_BYTES(32*1024*1024-128*1024)'),
                     (marker, marker + ports)]:
        assert template.count(old) == 1
        template = template.replace(old, new)
    monitor = '''
  bit linux_entry_seen, linux_user_seen, linux_user_vector_seen;
  bit linux_watch;
  longint unsigned linux_cycles, linux_last_retire;
  logic [63:0] linux_last_pc;
  initial linux_watch=$test$plusargs("linux_watch");
  always @(posedge clk) if (rst_n && load_done) begin
    linux_cycles++;
    for (int lane=0; lane<2; lane++) if (trace_valid[lane] && !trace_trap[lane]) begin
      linux_last_retire=linux_cycles;
      linux_last_pc=trace_pc[lane];
      if (!linux_entry_seen && trace_pc[lane]==64'h80200000 &&
          u_dut.u_cached_core.u_core.u_backend.current_privilege==rv_ooo_pkg::PRIV_S) begin
        linux_entry_seen=1;
        $display("\\nLINUX_RTL_S_ENTRY pc=%h",trace_pc[lane]);
        $fflush();
      end
      if (linux_entry_seen && !linux_user_seen &&
          u_dut.u_cached_core.u_core.u_backend.current_privilege==rv_ooo_pkg::PRIV_U) begin
        linux_user_seen=1;
        $display("\\nLINUX_RTL_U_RETIRE pc=%h",trace_pc[lane]);
        $fflush();
      end
      if (linux_entry_seen && !linux_user_vector_seen &&
          u_dut.u_cached_core.u_core.u_backend.current_privilege==rv_ooo_pkg::PRIV_U &&
          trace_instr[lane][6:0]==7'h57 && trace_instr[lane][14:12]!=3'b111) begin
        linux_user_vector_seen=1;
        $display("\\nLINUX_RTL_U_VECTOR_RETIRE pc=%h instruction=%h",trace_pc[lane],trace_instr[lane]);
        $fflush();
      end
    end
    if (linux_watch && linux_cycles%1000000==0) begin
      $display("\\nLINUX_RTL_WATCH cycles=%0d commits=%0d last_pc=%h idle_cycles=%0d priv=%0d",
               linux_cycles,commits,linux_last_pc,linux_cycles-linux_last_retire,
               u_dut.u_cached_core.u_core.u_backend.current_privilege);
      $fflush();
    end
  end
'''
    assert template.count('\nendmodule') == 1
    template = template.replace('\nendmodule', monitor + 'endmodule')
    generated = folder / 'rv_act4_program_tb.sv'
    generated.write_text(template, encoding='utf-8')
    files += ['tb/e2e/dpi/rv_host_dpi.sv', 'tb/e2e/dpi/rv_commit_trace_logger.sv',
              generated.relative_to(ROOT).as_posix(), 'tb/e2e/dpi/elf_loader.cpp']
    with Simulator() as sim:
        name = 'rv23_linux_sim_diagnostic' if args.diagnostic else 'rv23_linux_sim'
        if args.variant:
            name += '_' + args.variant
        build = sim.build(name, model['top'], files, model['params'])
    build.update(sram_kib=32768, base_model_sha256=sha(model_path),
                 overridden_sources=originals, firmware_sha256=sha(firmware), mailboxes=mailboxes)
    dump(folder / 'model.json', build)


if __name__ == '__main__':
    main()

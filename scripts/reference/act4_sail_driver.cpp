// SPDX-License-Identifier: BSD-2-Clause
// Bounded local ELF/HTIF driver for the unmodified upstream Sail ModelImpl.
#include "config_utils.h"
#include "elf_loader.h"
#include "file_utils.h"
#include "riscv_callbacks_log.h"
#include "riscv_model_impl.h"
#include "sail_config.h"
#include "sail_trace_callbacks.h"
#include "sail_riscv_version.h"
#include <iostream>
#include <stdexcept>

int main(int argc, char **argv) {
  try {
    std::string config, input, commit_csv, signature, trace_output;
    uint64_t limit = 10000000;
    unsigned granularity = 8;
    bool trace = false, validate = false;
    for (int i = 1; i < argc; ++i) {
      std::string arg = argv[i];
      auto value = [&]() -> std::string {
        if (++i == argc) throw std::runtime_error("Missing argument for " + arg);
        return argv[i];
      };
      if (arg == "--version") {
        std::cout << version_info::release_version() << "\n";
        return 0;
      } else if (arg == "--config") config = value();
      else if (arg == "--commit-csv") commit_csv = value();
      else if (arg == "--test-signature") signature = value();
      else if (arg.rfind("--test-signature=",0)==0) signature = arg.substr(17);
      else if (arg == "--signature-granularity") granularity = static_cast<unsigned>(std::stoul(value()));
      else if (arg == "--trace-output") trace_output = value();
      else if (arg == "--inst-limit") limit = std::stoull(value());
      else if (arg == "--trace") trace = true;
      else if (arg == "--validate-config") validate = true;
      else if (!arg.empty() && arg[0] != '-' && input.empty()) input = arg;
      else throw std::runtime_error("Unsupported driver argument: " + arg);
    }
    if (config.empty() || limit == 0) throw std::runtime_error("A config and finite instruction limit are required");
    const auto config_text = read_file_to_string(config);
    validate_config_schema(jsoncons::json::parse(config_text), config);
    sail_config_set_string(config_text.c_str());
    ModelImpl model;
    model.init_platform_constants();
    model.model_init();
    if (!model.config_is_valid()) throw std::runtime_error("Invalid Sail configuration");
    if (validate) {
      model.model_fini();
      std::cout << "PASS Sail model configuration\n";
      return 0;
    }
    const auto elf = ELF::open(input);
    if (elf.architecture() != Architecture::RV64 || model.xlen() != 64)
      throw std::runtime_error("Driver requires RV64 ELF and RV64 model");
    auto symbols = elf.symbols();
    if (!symbols.count("tohost")) throw std::runtime_error("ELF must define tohost");
#ifdef ACT4_SAIL_016
    const auto regions = model.memory_regions();
#else
    const auto regions = model.main_memory_regions();
#endif
    elf.load([&](uint64_t address, const uint8_t *data, uint64_t length) {
      bool covered = false;
      for (const auto &region : regions)
        covered |= address >= region.base && length <= region.size &&
                   address - region.base <= region.size - length;
      if (!covered) throw std::runtime_error("ELF segment exceeds configured memory");
      for (uint64_t i = 0; i < length; ++i) write_mem(address + i, data[i]);
    });
    std::map<uint64_t, std::string> reverse_symbols;
    for (const auto &entry : symbols) reverse_symbols[entry.second] = entry.first;
    model.set_elf_symbols(std::move(reverse_symbols));
    FILE *trace_stream = stdout;
    if (!trace_output.empty()) {
      trace_stream = fopen(trace_output.c_str(), "w");
      if (!trace_stream) throw std::runtime_error("Cannot open Sail trace output");
    }
    model.set_trace_log(trace_stream);
    model.set_config_print_instr(trace);
    model.set_config_print_exception(trace);
    if (trace) model.register_callback(std::make_shared<log_callbacks>(
        true, true, true, true, true, false, false, false, trace_stream));
    model.init_sail(elf.entry(), config.c_str(), symbols.at("tohost"));
    if (!commit_csv.empty()) model.register_callback(std::make_shared<CommitCallbacks>(commit_csv));
    uint64_t steps = 0, attempts = 0, wait_left = 0, tick_count = 0;
    const auto max_wait = get_config_uint64({"platform", "max_time_to_wait"});
    const auto per_tick = get_config_uint64({"platform", "instructions_per_tick"});
    bool waiting = false;
    while (!model.htif_done() && steps < limit && attempts < limit * 128) {
      ++attempts;
      model.call_pre_step_callbacks(waiting);
      waiting = model.try_step(static_cast<int64_t>(steps), wait_left == 0);
      if (const auto error = model.string_of_current_exception(); error)
        throw std::runtime_error(*error);
      if (waiting) wait_left = wait_left == 0 ? max_wait : wait_left - 1;
      else wait_left = 0;
      model.call_post_step_callbacks(waiting);
      if (!waiting) { ++steps; ++tick_count; }
      if (tick_count == per_tick) { tick_count = 0; model.tick_clock(); }
      else if (wait_left > 0) model.tick_clock();
    }
    const bool done = model.htif_done();
    const auto exit_code = model.htif_exit_code();
    const auto pc = model.pc();
    if (done && exit_code==0 && !signature.empty()) {
      if (!symbols.count("begin_signature") || !symbols.count("end_signature") || granularity==0 || granularity>16)
        throw std::runtime_error("Invalid signature range/granularity");
      uint64_t begin=symbols.at("begin_signature"), end=symbols.at("end_signature");
      if (end<begin || end-begin>1048576) throw std::runtime_error("Invalid signature bounds");
      FILE *sig=fopen(signature.c_str(), "w");
      if (!sig) throw std::runtime_error("Cannot open signature output");
      for (uint64_t address=begin;address<end;address+=granularity) {
        for (unsigned i=granularity;i>0;--i) fprintf(sig,"%02x",static_cast<unsigned>(read_mem(address+i-1)&255));
        fputc('\n',sig);
      }
      fclose(sig);
    }
    model.model_fini();
    if (trace_stream!=stdout) fclose(trace_stream);
    if (!done || exit_code != 0) {
      std::cerr << "FAIL Sail HTIF done=" << done << " exit=" << exit_code
                << " steps=" << steps << " pc=0x" << std::hex << pc << '\n';
      return 1;
    }
    std::cout << "PASS Sail HTIF steps=" << steps << " exit=0\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "FAIL Sail driver: " << error.what() << '\n';
    return 1;
  }
}

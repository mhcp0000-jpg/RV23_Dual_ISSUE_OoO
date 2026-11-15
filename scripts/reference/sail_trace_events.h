// SPDX-License-Identifier: BSD-2-Clause
#pragma once
#include "riscv_callbacks_if.h"
#include <cinttypes>
#include <cstdio>
#include <stdexcept>

// Trace observation only: do not change ModelImpl or instruction execution.
// A fetched WFI is recorded even when its step enters the wait state. Traps
// before fetch have an explicit interrupt flag and a zero instruction field.
class CommitCallbacks final : public callbacks_if {
  FILE *stream;
  uint64_t pc=0, instruction=0, data=0, cause=0;
  unsigned rd=0;
  bool fetched=false, write=false, fp=false, trap=false, interrupt=false;
public:
  explicit CommitCallbacks(const std::string &path) : stream(fopen(path.c_str(), "w")) {
    if (!stream) throw std::runtime_error("Cannot open reference event CSV");
    fputs("pc,instruction,rd_write,rd_fp,rd,wdata,trap,cause,interrupt,waiting,fetched\n", stream);
  }
  ~CommitCallbacks() override { fclose(stream); }
  void pre_step_callback(ModelImpl &model, bool) override {
    pc=model.pc(); instruction=data=cause=0; rd=0;
    fetched=write=fp=trap=interrupt=false;
  }
  void fetch_callback(ModelImpl &, sbits opcode) override {
    fetched=true; instruction=opcode.bits;
  }
  void xreg_full_write_callback(ModelImpl &, const_sail_string, sbits reg, sbits value) override {
    if (reg.bits != 0) { write=true; fp=false; rd=static_cast<unsigned>(reg.bits); data=value.bits; }
  }
  void freg_write_callback(ModelImpl &, unsigned reg, sbits value) override {
    write=fp=true; rd=reg; data=value.bits;
  }
  void trap_callback(ModelImpl &, bool is_interrupt, fbits code) override {
    trap=true; interrupt=is_interrupt; cause=code;
  }
  void post_step_callback(ModelImpl &, bool waiting) override {
    if (fetched || trap)
      fprintf(stream, "%016" PRIx64 ",%08" PRIx64 ",%d,%d,%u,%016" PRIx64 ",%d,%" PRIu64 ",%d,%d,%d\n",
              pc,instruction,write,fp,rd,data,trap,cause,interrupt,waiting,fetched);
  }
};

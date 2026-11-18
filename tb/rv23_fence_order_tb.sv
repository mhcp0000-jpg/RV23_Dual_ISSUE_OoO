`timescale 1ns/1ps
module rv23_fence_order_tb;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();

  localparam logic [31:0] WRITE_ADDR = 32'h80020000;
  localparam logic [31:0] READ_ADDR = 32'h80020040;
  localparam logic [31:0] ATOMIC_ADDR = 32'h80020080;
  localparam logic [31:0] MSIP_ADDR = 32'h02000000;
  localparam logic [31:0] ZERO_BLOCK = 32'h80020100;
  localparam logic [63:0] DEBUG_VALUE = 64'h13579bdf2468ace0;
  longint unsigned cycle = 0;
  bit program_started;
  bit pending[64];
  bit pending_write[64];
  bit atomic_pending;
  logic [31:0] pending_addr[64];
  int unsigned zero_writes = 0;

  initial begin
    wait (zero_writes == 1);
    core.u_host.write_register64(ZERO_BLOCK, DEBUG_VALUE);
  end

  `define BACKEND core.u_dut.u_core.u_backend
  always @(posedge core.clk) if (core.rst_n && core.load_done) begin
    cycle++;
    if (core.u_dut.sram_write_snoop &&
        core.u_dut.sram_write_snoop_addr[31:6] == ZERO_BLOCK[31:6]) begin
      if (core.u_dut.sram_write_snoop_data == 0) begin
        if (core.u_dut.sram_write_snoop_strb != 8'hff)
          $fatal(1, "Incomplete CBO.ZERO write beat");
        zero_writes++;
        $display("FENCE_ORDER %0d zero_beat %08h", cycle, core.u_dut.sram_write_snoop_addr);
      end else if (core.u_dut.sram_write_snoop_data == DEBUG_VALUE) begin
        if (core.u_dut.sram_write_snoop_addr != ZERO_BLOCK ||
            core.u_dut.sram_write_snoop_strb != 8'hff)
          $fatal(1, "Unexpected debug write shape");
        $display("FENCE_ORDER %0d debug_write %08h", cycle, ZERO_BLOCK);
      end
    end
    if (`BACKEND.vector_active_q && `BACKEND.vector_memory_valid && `BACKEND.cbo_write_ready_i &&
        !`BACKEND.vector_memory_write)
      $display("FENCE_ORDER %0d vector_read %08h", cycle, `BACKEND.vector_memory_address);
    for (int lane = 0; lane < 2; lane++)
      if (core.trace_valid[lane] && core.trace_pc[lane] >= 64'h80000000)
        program_started = 1;
    if (`BACKEND.head_special_request && `BACKEND.head_is_fence && !`BACKEND.lsu_memory_idle)
      $display("FENCE_ORDER %0d wait %08h", cycle, `BACKEND.rob_head_instruction);
    if (`BACKEND.atomic_valid_o && `BACKEND.atomic_ready_i && `BACKEND.atomic_address_o == ATOMIC_ADDR) begin
      if (atomic_pending) $fatal(1, "Overlapping atomic requests");
      atomic_pending = 1;
      $display("FENCE_ORDER %0d atomic_request %08h", cycle, ATOMIC_ADDR);
    end
    if (atomic_pending && `BACKEND.atomic_response_valid_i && `BACKEND.atomic_response_ready_o) begin
      $display("FENCE_ORDER %0d atomic_response %08h", cycle, ATOMIC_ADDR);
      atomic_pending = 0;
    end

    for (int lane = 0; lane < 2; lane++) begin
      logic [5:0] response_id;
      response_id = `BACKEND.dmem_rsp_id_i[lane];
      if (pending[response_id] && `BACKEND.dmem_rsp_valid_i[lane] && `BACKEND.dmem_rsp_ready_o[lane]) begin
        if (`BACKEND.dmem_rsp_resp_i[lane] != 0 || `BACKEND.dmem_rsp_replay_i[lane] != 0)
          $fatal(1, "Unexpected fixture response");
        $display("FENCE_ORDER %0d %0s_response %08h", cycle,
                 pending_write[response_id] ? "write" : "read", pending_addr[response_id]);
        pending[response_id] = 0;
      end
      if (core.trace_valid[lane] && !core.trace_trap[lane] &&
          core.trace_instr[lane][6:0] == 7'h0f && core.trace_instr[lane][14:12] == 0)
        $display("FENCE_ORDER %0d retire %08h", cycle, core.trace_instr[lane]);
      if (core.trace_valid[lane] && !core.trace_trap[lane] && core.trace_instr[lane][6:0] == 7'h2f)
        $display("FENCE_ORDER %0d atomic_retire %08h", cycle, core.trace_instr[lane]);
      if (core.trace_valid[lane] && !core.trace_trap[lane] &&
          core.trace_instr[lane] inside {32'h004a200f, 32'h020af407})
        $display("FENCE_ORDER %0d block_retire %08h", cycle, core.trace_instr[lane]);
    end
    for (int lane = 0; lane < 2; lane++) begin
      logic [5:0] request_id;
      logic [31:0] address;
      request_id = `BACKEND.dmem_req_id_o[lane];
      address = `BACKEND.dmem_req_addr_o[lane];
      if (program_started && `BACKEND.dmem_req_valid_o[lane] && `BACKEND.dmem_req_ready_i[lane] &&
          address inside {WRITE_ADDR, READ_ADDR, MSIP_ADDR}) begin
        if (pending[request_id]) $fatal(1, "Fixture reuses a pending ID");
        pending[request_id] = 1;
        pending_write[request_id] = `BACKEND.dmem_req_write_o[lane];
        pending_addr[request_id] = address;
        $display("FENCE_ORDER %0d %0s_request %08h", cycle,
                 pending_write[request_id] ? "write" : "read", address);
      end
    end
  end
  `undef BACKEND
endmodule

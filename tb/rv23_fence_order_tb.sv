`timescale 1ns/1ps
module rv23_fence_order_tb;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();

  localparam logic [31:0] WRITE_ADDR = 32'h80020000;
  localparam logic [31:0] READ_ADDR = 32'h80020040;
  longint unsigned cycle = 0;
  logic [5:0] store_id;
  bit store_pending = 0;

  `define BACKEND core.u_dut.u_core.u_backend
  always @(posedge core.clk) if (core.rst_n && core.load_done) begin
    cycle++;
    if (`BACKEND.head_special_request && `BACKEND.head_is_fence && !`BACKEND.lsu_memory_idle)
      $display("FENCE_ORDER %0d wait %08h", cycle, `BACKEND.rob_head_instruction);

    for (int lane = 0; lane < 2; lane++) begin
      if (store_pending && `BACKEND.dmem_rsp_valid_i[lane] && `BACKEND.dmem_rsp_ready_o[lane] &&
          `BACKEND.dmem_rsp_id_i[lane] == store_id) begin
        if (`BACKEND.dmem_rsp_resp_i[lane] != 0 || `BACKEND.dmem_rsp_replay_i[lane] != 0)
          $fatal(1, "Unexpected write response");
        $display("FENCE_ORDER %0d write_response %08h", cycle, WRITE_ADDR);
        store_pending = 0;
      end
      if (`BACKEND.dmem_req_valid_o[lane] && `BACKEND.dmem_req_ready_i[lane]) begin
        if (`BACKEND.dmem_req_write_o[lane] && `BACKEND.dmem_req_addr_o[lane] == WRITE_ADDR) begin
          if (store_pending) $fatal(1, "Overlapping fixture writes");
          store_id = `BACKEND.dmem_req_id_o[lane];
          store_pending = 1;
          $display("FENCE_ORDER %0d write_request %08h", cycle, WRITE_ADDR);
        end
        if (!`BACKEND.dmem_req_write_o[lane] && `BACKEND.dmem_req_addr_o[lane] == READ_ADDR)
          $display("FENCE_ORDER %0d read_request %08h", cycle, READ_ADDR);
      end
      if (core.trace_valid[lane] && !core.trace_trap[lane] &&
          core.trace_instr[lane][14:0] == 15'h000f)
        $display("FENCE_ORDER %0d retire %08h", cycle, core.trace_instr[lane]);
      // The forward-compatibility probe encodes a nonzero rd.
      if (core.trace_valid[lane] && !core.trace_trap[lane] &&
          core.trace_instr[lane] == 32'hf230830f)
        $display("FENCE_ORDER %0d retire %08h", cycle, core.trace_instr[lane]);
    end
  end
  `undef BACKEND
endmodule

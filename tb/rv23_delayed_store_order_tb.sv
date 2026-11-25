`timescale 1ns/1ps
module rv23_delayed_store_order_tb;
  import rv_ooo_pkg::*;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();
  `define LSU core.u_dut.u_cached_core.u_core.u_backend.u_lsu_cluster.u_lsq
  `define DIV core.u_dut.u_cached_core.u_core.u_backend.u_div
  bit program_started=0;
  longint unsigned unknown_cycles=0,partial_cycles=0,data_cycles=0,div_overlap=0,older_sq_div=0;
  always @(posedge core.clk) if(core.rst_n && core.load_done) begin
    for(int lane=0;lane<2;lane++)
      if(core.trace_valid[lane] && core.trace_pc[lane]>=64'h80000000) program_started=1;
    for(int lane=0;lane<2;lane++) begin
      if(program_started && `LSU.load_candidate_present_o[lane] && `LSU.load_stall_reason_o[lane] inside
        {LSQ_STALL_UNKNOWN_ADDR,LSQ_STALL_PARTIAL_OVERLAP,LSQ_STALL_STORE_DATA}) begin
        if(`LSU.load_memory_read_o[lane] || `LSU.load_forward_valid_o[lane] ||
           `LSU.load_candidate_valid_o[lane]) $fatal(1,"Blocked load escaped ordering check");
        case(`LSU.load_stall_reason_o[lane])
          LSQ_STALL_UNKNOWN_ADDR: begin
            bit older_unknown_store;
            older_unknown_store=0;
            unknown_cycles++;
            for(int store=0;store<$bits(`LSU.sq_valid_q);store++)begin
              logic [ROB_SEQ_WIDTH-1:0] age;
              age=`LSU.load_candidate_sequence_o[lane]-`LSU.sq_sequence_q[store];
              if(`LSU.sq_valid_q[store] && !`LSU.sq_address_valid_q[store] &&
                 age!=0 && !age[ROB_SEQ_WIDTH-1]) older_unknown_store=1;
            end
            if(`DIV.busy_q) begin
              div_overlap++;
              if(older_unknown_store) older_sq_div++;
            end
          end
          LSQ_STALL_PARTIAL_OVERLAP:partial_cycles++;
          LSQ_STALL_STORE_DATA:data_cycles++;
          default:;
        endcase
      end
    end
  end
  final begin
    $display("DELAYED_STORE_ORDER unknown=%0d partial=%0d data=%0d div_overlap=%0d older_sq_div=%0d",
      unknown_cycles,partial_cycles,data_cycles,div_overlap,older_sq_div);
  end
  `undef LSU
  `undef DIV
endmodule

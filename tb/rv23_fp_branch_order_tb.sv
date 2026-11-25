`timescale 1ns/1ps
module rv23_fp_branch_order_tb;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();
  localparam int SEQ_W=rv_ooo_pkg::ROB_SEQ_WIDTH;
  logic [63:0] wrong_pc[8], begin_pc[8], end_pc[8];
  logic [SEQ_W-1:0] wrong_seq[8];
  logic [7:0] dispatched='0, accepted='0, completed='0, recovered='0, active='0;
  logic slow_killed=0, check_idle=0;
`define B core.u_dut.u_cached_core.u_core.u_backend
  function automatic bit younger(input logic [SEQ_W-1:0] lhs,rhs);
    logic [SEQ_W-1:0] delta;
    delta=lhs-rhs;
    return $signed(delta)>0;
  endfunction
  initial begin
    for(int i=0;i<8;i++) begin
      wrong_seq[i]='0;
      if(!$value$plusargs($sformatf("wrong%0d=%%h",i),wrong_pc[i]) ||
         !$value$plusargs($sformatf("wrong_begin%0d=%%h",i),begin_pc[i]) ||
         !$value$plusargs($sformatf("wrong_end%0d=%%h",i),end_pc[i]))
        $fatal(1,"Missing FP wrong-path PC range");
    end
  end
  always @(posedge core.clk) if(core.rst_n && core.load_done) begin
    if(check_idle) begin
      if(`B.g_profile_fpu.u_fpu.state_q!=0 || `B.fpu_result_valid)
        $fatal(1,"Killed FP slow owner survived flush");
      check_idle=0;
    end
    for(int i=0;i<8;i++) begin
      if(`B.dispatch_fire)
        for(int lane=0;lane<2;lane++)
          if(`B.dec_valid[lane] && `B.dec_pc[lane]==wrong_pc[i]) begin
            dispatched[i]=1;
            active[i]=1;
            wrong_seq[i]=`B.rob_alloc_sequence[lane];
          end
      if(active[i] && `B.fpu_issue_valid_q && `B.fpu_req_ready && !`B.flush_valid &&
         `B.fpu_issue_sequence_q==wrong_seq[i]) accepted[i]=1;
      if(active[i] && `B.fpu_result_valid && `B.fpu_result_ready &&
         `B.fpu_result_sequence==wrong_seq[i]) completed[i]=1;
      if(active[i] && `B.flush_valid && !`B.flush_all && younger(wrong_seq[i],`B.flush_sequence)) begin
        recovered[i]=1;
        if(i==6 && accepted[i] && `B.g_profile_fpu.u_fpu.sequence_q==wrong_seq[i] &&
           `B.g_profile_fpu.u_fpu.state_q==2) begin
          slow_killed=1;
          check_idle=1;
        end
        active[i]=0;
      end
      for(int lane=0;lane<2;lane++)
        if(core.trace_valid[lane] && core.trace_pc[lane]>=begin_pc[i] && core.trace_pc[lane]<end_pc[i])
          $fatal(1,"Wrong-path FP region retired/trapped");
    end
  end
  final begin
    if(dispatched!=8'hff || accepted!=8'h4f || (completed&8'h0f)!=8'h0f ||
       completed[6] || recovered!=8'hff || !slow_killed)
      $error("Missing FP speculation/completion/in-flight slow kill coverage");
    $display("FP BRANCH ORDER dispatched=%02h accepted=%02h completed=%02h recovered=%02h slow_killed=%0d",
      dispatched,accepted,completed,recovered,slow_killed);
  end
`undef B
endmodule

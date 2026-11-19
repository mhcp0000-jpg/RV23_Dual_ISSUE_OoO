`timescale 1ns/1ps
module rv23_vector_scalar_overlap_tb;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();
`define B core.u_dut.u_core.u_backend
  int int_overlap=0,fp_overlap=0,fp_coretire=0,busy_start=0,branch_keep=0;
  always @(posedge core.clk)if(core.rst_n && core.load_done)begin
    if(`B.vector_active_q)begin
      for(int p=0;p<2;p++)
        if(`B.fast_req_valid[p] && `B.fast_req_ready[p] &&
           `B.sequence_after_backend(`B.fast_req_sequence[p],`B.rob_head_sequence))int_overlap++;
      if(`B.port_valid[4] && `B.fpu_req_ready &&
         `B.sequence_after_backend(`B.port_sequence[4],`B.rob_head_sequence))fp_overlap++;
      if(`B.flush_valid && !`B.flush_all)branch_keep++;
    end
    if(`B.vector_start && `B.vector_request_ready && !`B.vector_head_decode.memory && !`B.lsu_memory_idle)
      busy_start++;
    if(`B.head_is_vector && (&`B.retire_fire) && core.trace_fp[1] && core.trace_we[1])fp_coretire++;
    if(`B.vector_start && `B.vector_head_decode.memory && !`B.lsu_memory_idle)
      $fatal(1,"Memory vector bypassed its ordering drain");
  end
  final begin
    $display("VECTOR_SCALAR_OVERLAP int=%0d fp=%0d fp_coretire=%0d busy_start=%0d branch_keep=%0d",
      int_overlap,fp_overlap,fp_coretire,busy_start,branch_keep);
    if(int_overlap==0 || fp_overlap==0 || fp_coretire==0 || busy_start==0 || branch_keep==0)
      $error("Missing scalar/vector overlap witness");
  end
`undef B
endmodule

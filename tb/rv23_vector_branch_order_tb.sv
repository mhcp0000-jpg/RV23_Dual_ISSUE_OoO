`timescale 1ns/1ps
module rv23_vector_branch_order_tb;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();
  logic [63:0] wrong_pc[6];
  logic [5:0] dispatched='0, recovered='0;
  initial begin
    for(int i=0;i<6;i++) begin
      if(!$value$plusargs($sformatf("wrong%0d=%%h",i),wrong_pc[i]))
        $fatal(1,"Missing wrong-path PC");
    end
  end
  always @(posedge core.clk) if(core.rst_n && core.load_done) begin
    for(int i=0;i<6;i++) begin
      if(core.u_dut.u_cached_core.u_core.u_backend.dispatch_fire)
        for(int lane=0;lane<2;lane++)
          if(core.u_dut.u_cached_core.u_core.u_backend.dec_valid[lane] &&
             core.u_dut.u_cached_core.u_core.u_backend.dec_pc[lane]==wrong_pc[i]) dispatched[i]=1;
      if(core.u_dut.u_cached_core.u_core.u_backend.flush_valid && dispatched[i]) recovered[i]=1;
      if(core.u_dut.u_cached_core.u_core.u_backend.vector_start &&
         core.u_dut.u_cached_core.u_core.u_backend.rob_head_pc==wrong_pc[i])
        $fatal(1,"Wrong-path vector executed");
      for(int lane=0;lane<2;lane++)
        if(core.trace_valid[lane] && core.trace_pc[lane]==wrong_pc[i])
          $fatal(1,"Wrong-path vector retired/trapped");
    end
  end
  final begin
    if(dispatched!='1 || recovered!='1) $error("Missing speculative vector/recovery coverage");
    $display("VECTOR BRANCH ORDER dispatched=%02h recovered=%02h",dispatched,recovered);
  end
endmodule

// Reuse the functional owner stream; count preflight work independently.
module rv23_memory_preflight_perf_tb;
  rv23_hypervisor_memory_head_tb core();
  int checks=0,aligned_checks=0,requests=0;
  always @(posedge core.clk)if(core.rst_n)begin
    // CHECK is enum ordinal 3 in this owner. Avoid hierarchical enum-item
    // references, which trigger a Verilator 5.050 width-pass internal error.
    if(core.dut.state_q==3'd3)begin
      checks++;
      if(core.dut.natural_q)aligned_checks++;
    end
    if(core.mv && core.mr)requests++;
  end
  final $display("PREFLIGHT_PERF cycles=%0d checks=%0d aligned_checks=%0d requests=%0d",
    core.ticks,checks,aligned_checks,requests);
endmodule

module rv23_elab;
  logic clk_i, rst_ni;
  rv_axi4_if #(.ID_WIDTH(4)) dbg32 (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) dbg64 (.clk_i,.rst_ni);
  rv23_soc_top #(.XLEN(32)) u32 (.clk_i,.rst_ni,.core_run_i(1'b1),
    .debug_axi_s(dbg32),.debug_halt_req_i(1'b0),.external_irq_i('0),
    .host_event_ready_i(1'b1));
  rv23_soc_top #(.XLEN(64),.HAS_V(1),.HAS_H(1),.PLIC_NUM_SOURCES(8)) u64 (.clk_i,.rst_ni,.core_run_i(1'b1),
    .debug_axi_s(dbg64),.debug_halt_req_i(1'b0),.external_irq_i('0),
    .host_event_ready_i(1'b1));
endmodule

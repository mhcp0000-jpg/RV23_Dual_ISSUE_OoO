module rv23_wait_reservation #(
  parameter int unsigned SHORT_CYCLES=1024,
  parameter int unsigned TRAP_CYCLES=2048,
  localparam int COUNT_WIDTH=$clog2((SHORT_CYCLES>TRAP_CYCLES?SHORT_CYCLES:TRAP_CYCLES)+1)
)(
  input logic clk_i,rst_ni,request_valid_i,short_timeout_i,
  input logic reservation_valid_i,interrupt_wake_i,debug_wake_i,
  input logic [1:0] privilege_i,
  input logic tw_i,virtual_i,vtw_i,
  output logic completion_valid_o,exception_o,
  output logic [5:0] cause_o
);
  logic [COUNT_WIDTH-1:0] elapsed_q;
  logic stop_wait,trap_wait;
  assign stop_wait=!reservation_valid_i || interrupt_wake_i || debug_wake_i;
  assign trap_wait=!short_timeout_i && !stop_wait &&
    elapsed_q>=COUNT_WIDTH'(TRAP_CYCLES-1) &&
    ((privilege_i!=3 && tw_i) || (virtual_i && vtw_i));
  assign completion_valid_o=request_valid_i && (stop_wait || trap_wait ||
    (short_timeout_i && elapsed_q>=COUNT_WIDTH'(SHORT_CYCLES-1)));
  assign exception_o=completion_valid_o && trap_wait;
  assign cause_o=tw_i?6'd2:6'd22;
  always_ff @(posedge clk_i) begin
    if(!rst_ni) elapsed_q<=0;
    else if(!request_valid_i) elapsed_q<=0;
    else if(!completion_valid_o && !(&elapsed_q)) elapsed_q<=elapsed_q+1'b1;
  end
  initial if(SHORT_CYCLES<1 || TRAP_CYCLES<1) $fatal(1,"Invalid WRS timeout");
endmodule

// One architectural vector element, using a bounded iterative divider instead
// of a combinational / or % cone. Hold all data classes to the same latency.
module rv_vector_divider(
  input logic clk_i,rst_ni,
  input logic request_valid_i,
  output logic request_ready_o,
  input logic [1:0] sew_size_i,
  input logic signed_i,remainder_i,
  input logic [63:0] operand_a_i,operand_b_i,
  output logic response_valid_o,
  input logic response_ready_i,
  output logic [63:0] result_o
);
  import rv_ooo_pkg::*;
  localparam int unsigned LATENCY=68;
  logic active_q,divider_ready,divider_valid;
  logic [6:0] remaining_q;
  logic [1:0] sew_q;
  logic [63:0] a,b,divider_result,mask;
  divide_op_e operation;
  always_comb begin
    case(sew_size_i)
      0:begin a=signed_i?{{56{operand_a_i[7]}},operand_a_i[7:0]}:{56'b0,operand_a_i[7:0]};
              b=signed_i?{{56{operand_b_i[7]}},operand_b_i[7:0]}:{56'b0,operand_b_i[7:0]};end
      1:begin a=signed_i?{{48{operand_a_i[15]}},operand_a_i[15:0]}:{48'b0,operand_a_i[15:0]};
              b=signed_i?{{48{operand_b_i[15]}},operand_b_i[15:0]}:{48'b0,operand_b_i[15:0]};end
      2:begin a=signed_i?{{32{operand_a_i[31]}},operand_a_i[31:0]}:{32'b0,operand_a_i[31:0]};
              b=signed_i?{{32{operand_b_i[31]}},operand_b_i[31:0]}:{32'b0,operand_b_i[31:0]};end
      default:begin a=operand_a_i;b=operand_b_i;end
    endcase
    operation=remainder_i?(signed_i?DIV_SIGNED_REMAINDER:DIV_UNSIGNED_REMAINDER):
      (signed_i?DIV_SIGNED_QUOTIENT:DIV_UNSIGNED_QUOTIENT);
    case(sew_q)
      0:mask=64'hff;1:mask=64'hffff;2:mask=64'hffffffff;default:mask='1;
    endcase
  end
  assign request_ready_o=!active_q && divider_ready;
  assign response_valid_o=active_q && remaining_q==0 && divider_valid;
  assign result_o=divider_result & mask;
  rv_divider #(.XLEN(64)) u_div(
    .clk_i,.rst_ni,.request_valid_i(request_valid_i && !active_q),.request_ready_o(divider_ready),
    .operand_a_i(a),.operand_b_i(b),.operation_i(operation),.word_operation_i(1'b0),
    .request_rob_sequence_i('0),.request_destination_valid_i(1'b1),.request_destination_phys_i('0),
    .flush_valid_i(1'b0),.flush_all_i(1'b0),.flush_sequence_i('0),
    .result_valid_o(divider_valid),.result_ready_i(response_ready_i && active_q && remaining_q==0),
    .result_o(divider_result),.result_rob_sequence_o(),.result_destination_valid_o(),.result_destination_phys_o());
  always_ff @(posedge clk_i)begin
    if(!rst_ni)begin active_q<=0;remaining_q<=0;sew_q<=0;end
    else begin
      if(request_valid_i && request_ready_o)begin active_q<=1;remaining_q<=7'(LATENCY);sew_q<=sew_size_i;end
      else if(active_q && remaining_q!=0)remaining_q<=remaining_q-1'b1;
      if(response_valid_o && response_ready_i)active_q<=0;
    end
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    response_valid_o && !response_ready_i |=> response_valid_o && $stable(result_o));
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    active_q |-> !request_ready_o);
`endif
endmodule

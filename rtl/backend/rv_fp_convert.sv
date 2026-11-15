// Direct IEEE half/single/double conversions, with architectural NaN boxing.
// Every conversion rounds once at its destination precision.
module rv_fp_convert(
  input logic [63:0] operand_i,
  input logic [1:0] source_format_i,destination_format_i,
  input logic [2:0] rounding_i,
  output logic [63:0] result_o,
  output logic [4:0] flags_o
);
  localparam int EXP[3]='{8,11,5};
  localparam int SIG[3]='{24,53,11};
  localparam int WIDTH[3]='{32,64,16};
  logic [63:0] normalized[3];
  logic [63:0] result[3][3];
  logic [4:0] flags[3][3];
  assign normalized[0]= (&operand_i[63:32]) ? operand_i:64'hffffffff7fc00000;
  assign normalized[1]=operand_i;
  assign normalized[2]= (&operand_i[63:16]) ? operand_i:64'hffffffffffff7e00;
  for(genvar s=0;s<3;s++) begin:g_source
    wire [WIDTH[s]:0] recoded;
    fNToRecFN #(EXP[s],SIG[s]) u_in(.in(normalized[s][WIDTH[s]-1:0]),.out(recoded));
    for(genvar d=0;d<3;d++) begin:g_destination
      wire [WIDTH[d]:0] converted;
      wire [WIDTH[d]-1:0] ieee_result;
      recFNToRecFN #(EXP[s],SIG[s],EXP[d],SIG[d]) u_convert(
        .control(1'b1),.in(recoded),.roundingMode(rounding_i),.out(converted),.exceptionFlags(flags[s][d]));
      recFNToFN #(EXP[d],SIG[d]) u_out(.in(converted),.out(ieee_result));
      assign result[s][d]={{(64-WIDTH[d]){1'b1}},ieee_result};
    end
  end
  always_comb begin
    result_o=64'h7ff8000000000000;flags_o=5'b10000;
    if(source_format_i<3 && destination_format_i<3) begin
      result_o=result[source_format_i][destination_format_i];
      flags_o=flags[source_format_i][destination_format_i];
    end
  end
endmodule

// Raw vector-element conversions, including I16<->F32. Conversion width is
// architectural: converting to I32 then truncating to I16 gives wrong NV/data.
module rv_vector_fp_integer (
  input logic [63:0] operand_i,
  input logic fp_double_i,
  input logic [1:0] integer_size_i,
  input logic unsigned_i,to_float_i,
  input logic [2:0] rounding_i,
  output logic [63:0] result_o,
  output logic [4:0] flags_o
);
  localparam int EXP[2]='{8,11};
  localparam int SIG[2]='{24,53};
  localparam int WIDTH[2]='{32,64};
  logic [63:0] float_result[2][4],integer_result[2][4];
  logic [4:0] from_flags[2][4],to_flags[2][4];
  for(genvar f=0;f<2;f++) begin:g_float
    wire [WIDTH[f]:0] recoded_input;
    fNToRecFN #(EXP[f],SIG[f]) u_input(.in(operand_i[WIDTH[f]-1:0]),.out(recoded_input));
    for(genvar i=0;i<4;i++) begin:g_integer
      localparam int IW=8<<i;
      wire [WIDTH[f]:0] recoded_output;
      wire [WIDTH[f]-1:0] ieee_output;
      wire [IW-1:0] converted_integer;
      wire [2:0] integer_flags;
      iNToRecFN #(IW,EXP[f],SIG[f]) u_from(.control(1'b1),.signedIn(!unsigned_i),
        .in(operand_i[IW-1:0]),.roundingMode(rounding_i),.out(recoded_output),.exceptionFlags(from_flags[f][i]));
      recFNToFN #(EXP[f],SIG[f]) u_float_output(.in(recoded_output),.out(ieee_output));
      recFNToIN #(EXP[f],SIG[f],IW) u_to(.control(1'b1),.in(recoded_input),
        .roundingMode(rounding_i),.signedOut(!unsigned_i),.out(converted_integer),.intExceptionFlags(integer_flags));
      assign float_result[f][i]=64'(ieee_output);
      assign integer_result[f][i]=64'(converted_integer);
      assign to_flags[f][i]={|integer_flags[2:1],3'b0,integer_flags[0]};
    end
  end
  always_comb begin
    result_o=to_float_i?float_result[fp_double_i][integer_size_i]:integer_result[fp_double_i][integer_size_i];
    flags_o=to_float_i?from_flags[fp_double_i][integer_size_i]:to_flags[fp_double_i][integer_size_i];
  end
endmodule

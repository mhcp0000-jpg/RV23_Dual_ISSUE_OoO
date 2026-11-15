// Zfa FROUND/FROUNDNX: integral-valued floating-point result. No intermediate
// fixed-width integer can overflow for large finite input values.
module rv_fp_round_to_int #(
  parameter int EXP=11,SIG=53,
  localparam int WIDTH=EXP+SIG
)(
  input logic [WIDTH-1:0] operand_i,
  input logic [2:0] rounding_i,
  input logic signal_inexact_i,
  output logic [WIDTH-1:0] result_o,
  output logic [4:0] flags_o
);
  localparam int BIAS=(1<<(EXP-1))-1;
  localparam logic [WIDTH-1:0] QNAN={1'b0,{EXP{1'b1}},1'b1,{(SIG-2){1'b0}}};
  logic negative,increment,inexact;
  logic [WIDTH-1:0] mask,discarded,half,unit_bit;
  integer exponent,drop;
  always_comb begin
    negative=operand_i[WIDTH-1];result_o=operand_i;flags_o=0;
    exponent=int'(operand_i[WIDTH-2-:EXP])-BIAS;
    increment=0;inexact=0;drop=0;mask=0;discarded=0;half=0;unit_bit=0;
    if(&operand_i[WIDTH-2-:EXP]) begin
      if(|operand_i[SIG-2:0]) begin
        result_o=QNAN;flags_o[4]=!operand_i[SIG-2];
      end
    end else if(operand_i[WIDTH-2:0]!=0 && exponent<SIG-1) begin
      if(exponent<0) begin
        inexact=1;
        case(rounding_i)
          0:increment=exponent==-1 && (|operand_i[SIG-2:0]);
          2:increment=negative;
          3:increment=!negative;
          4:increment=exponent==-1;
          default:increment=0;
        endcase
        result_o={negative,{(WIDTH-1){1'b0}}};
        if(increment) result_o=result_o | (WIDTH'(BIAS)<<(SIG-1));
      end else begin
        drop=SIG-1-exponent;
        unit_bit=WIDTH'(1)<<drop;mask=unit_bit-1'b1;
        discarded=operand_i & mask;half=unit_bit>>1;inexact=|discarded;
        case(rounding_i)
          0:increment=discarded>half || (discarded==half && operand_i[drop]);
          2:increment=inexact && negative;
          3:increment=inexact && !negative;
          4:increment=discarded>=half;
          default:increment=0;
        endcase
        result_o=(operand_i & ~mask)+(increment?unit_bit:WIDTH'(0));
      end
      flags_o[0]=signal_inexact_i && inexact;
    end
  end
endmodule

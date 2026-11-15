// Zfa's exact 32-entry FLI.S/FLI.D table. Half FLI requires Zfh, which is
// separate from this profile's Zfhmin and is not decoded by this implementation.
module rv_fp_immediate #(
  parameter int EXP=11,SIG=53,
  localparam int WIDTH=EXP+SIG
)(
  input logic [4:0] index_i,
  output logic [WIDTH-1:0] value_o
);
  localparam int BIAS=(1<<(EXP-1))-1;
  integer exponent;
  always_comb begin
    value_o=0;exponent=0;
    if(index_i>=8 && index_i<=22) begin
      exponent=BIAS+((int'(index_i)-8)/4)-2;
      value_o=(WIDTH'(exponent)<<(SIG-1)) | (WIDTH'(index_i[1:0])<<(SIG-3));
    end else case(index_i)
      0:value_o=(WIDTH'(1)<<(WIDTH-1)) | (WIDTH'(BIAS)<<(SIG-1));
      1:value_o=WIDTH'(1)<<(SIG-1);
      30:value_o={1'b0,{EXP{1'b1}},{(SIG-1){1'b0}}};
      31:value_o={1'b0,{EXP{1'b1}},1'b1,{(SIG-2){1'b0}}};
      default:begin
        case(index_i)
          2:exponent=-16;3:exponent=-15;4:exponent=-8;5:exponent=-7;
          6:exponent=-4;7:exponent=-3;23:exponent=2;24:exponent=3;
          25:exponent=4;26:exponent=7;27:exponent=8;28:exponent=15;29:exponent=16;
          default:exponent=0;
        endcase
        value_o=WIDTH'(exponent+BIAS)<<(SIG-1);
      end
    endcase
  end
  initial if(EXP<8 || SIG<3)$fatal(1,"FLI block supports single/double formats");
endmodule

// Exact RVV vfrec7/vfrsqrt7 approximation, including normalization and flags.
// Estimate precision is architectural; this is not exact division or sqrt.
module rv_vector_fp_estimate #(
  parameter int unsigned EXP=8,FRAC=23,
  localparam int unsigned WIDTH=1+EXP+FRAC
)(
  input logic [WIDTH-1:0] operand_i,
  input logic reciprocal_sqrt_i,
  input logic [2:0] rounding_i,
  output logic [WIDTH-1:0] result_o,
  output logic [4:0] flags_o
);
  import rv_vector_estimate_tables_pkg::*;
  localparam int BIAS=(1<<(EXP-1))-1;
  localparam logic [EXP-1:0] EXP_MAX={EXP{1'b1}};
  localparam logic [WIDTH-1:0] INF={1'b0,EXP_MAX,{FRAC{1'b0}}};
  localparam logic [WIDTH-1:0] NAN=INF|(WIDTH'(1)<<(FRAC-1));
  logic sign_bit,found,finite_overflow;
  logic [EXP-1:0] exponent;
  logic [FRAC-1:0] fraction,normalized_fraction,output_fraction;
  logic [FRAC:0] output_significand;
  int signed normalized_exponent,output_exponent;
  int unsigned leading,index;
  always_comb begin
    sign_bit=operand_i[WIDTH-1];exponent=operand_i[FRAC+:EXP];fraction=operand_i[FRAC-1:0];
    leading=0;found=0;
    for(int bit_index=FRAC-1;bit_index>=0;bit_index--)
      if(fraction[bit_index] && !found)begin leading=FRAC-1-bit_index;found=1;end
    normalized_exponent=int'(exponent);normalized_fraction=fraction;
    if(exponent==0 && fraction!=0)begin
      normalized_exponent=-int'(leading);normalized_fraction=fraction<<(leading+1);
    end
    output_exponent=0;output_fraction=0;output_significand=0;index=0;
    flags_o=0;result_o=0;
    finite_overflow=rounding_i==1 || (rounding_i==2 && !sign_bit) || (rounding_i==3 && sign_bit);
    if(exponent==EXP_MAX && fraction!=0)begin
      result_o=NAN;flags_o[4]=!fraction[FRAC-1];
    end else if(reciprocal_sqrt_i && sign_bit && (exponent!=0 || fraction!=0))begin
      result_o=NAN;flags_o[4]=1;
    end else if(exponent==0 && fraction==0)begin
      result_o={sign_bit,INF[WIDTH-2:0]};flags_o[3]=1;
    end else if(exponent==EXP_MAX)begin
      result_o=reciprocal_sqrt_i?'0:{sign_bit,{(WIDTH-1){1'b0}}};
    end else if(reciprocal_sqrt_i)begin
      index=((normalized_exponent&1)<<6)|int'(normalized_fraction>>(FRAC-6));
      output_fraction=FRAC'(RECIPROCAL_SQRT[index])<<(FRAC-7);
      output_exponent=(3*BIAS-1-normalized_exponent)/2;
      result_o={1'b0,EXP'(output_exponent),output_fraction};
    end else if(exponent==0 && normalized_exponent < -1)begin
      flags_o=5'b00101;
      result_o=finite_overflow?({sign_bit,INF[WIDTH-2:0]}-WIDTH'(1)):{sign_bit,INF[WIDTH-2:0]};
    end else begin
      index=int'(normalized_fraction>>(FRAC-7));
      output_fraction=FRAC'(RECIPROCAL[index])<<(FRAC-7);
      output_significand={1'b1,output_fraction};
      output_exponent=2*BIAS-1-normalized_exponent;
      if(output_exponent<=0)begin
        output_fraction=FRAC'(output_significand>>(1-output_exponent));output_exponent=0;
      end
      result_o={sign_bit,EXP'(output_exponent),output_fraction};
    end
  end
  initial if(!(WIDTH inside {16,32,64}) || FRAC<7)$fatal(1,"Unsupported vector estimate format");
endmodule

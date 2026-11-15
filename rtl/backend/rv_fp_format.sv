// Format-parameterized F/D arithmetic. Inputs are IEEE values after architectural
// NaN-box validation. The surrounding issue/result wrapper owns tags and flush.
// Berkeley HardFloat supplies synthesizable exact arithmetic, not DPI emulation.
module rv_fp_format #(
  parameter int EXP=11,SIG=53,
  localparam int WIDTH=EXP+SIG
)(
  input logic clk_i,rst_ni,
  input logic [31:0] instruction_i,
  input logic [63:0] a_i,b_i,c_i,
  input logic [2:0] rounding_i,
  output logic [63:0] fast_data_o,
  output logic [4:0] fast_flags_o,
  output logic fast_supported_o,
  input logic slow_valid_i,
  output logic slow_ready_o,slow_result_valid_o,
  output logic [WIDTH-1:0] slow_data_o,
  output logic [4:0] slow_flags_o
);
  localparam logic [WIDTH-1:0] QNAN={1'b0,{EXP{1'b1}},1'b1,{(SIG-2){1'b0}}};
  logic [WIDTH:0] a,b,c,add_result,mul_result,fma_result,from_int_result,slow_result;
  logic [WIDTH-1:0] add_ieee,mul_ieee,fma_ieee,from_int_ieee;
  logic [4:0] add_flags,mul_flags,fma_flags,from_int_flags,compare_flags;
  logic [2:0] int32_flags,int64_flags;
  logic [31:0] int32_result;
  logic [63:0] int64_result,integer_operand;
  logic less,equal,greater,unordered,signaling_compare;
  logic a_nan,b_nan,a_snan,b_snan,a_zero,b_zero;
  logic [9:0] classification;
  logic [WIDTH-1:0] selected_minmax;
  logic choose_max;
  logic [1:0] fma_op;
  assign fma_op={instruction_i[3],instruction_i[2]};
  fNToRecFN #(EXP,SIG) u_a(.in(a_i[WIDTH-1:0]),.out(a));
  fNToRecFN #(EXP,SIG) u_b(.in(b_i[WIDTH-1:0]),.out(b));
  fNToRecFN #(EXP,SIG) u_c(.in(c_i[WIDTH-1:0]),.out(c));
  addRecFN #(EXP,SIG) u_add(.control(1'b1),.subOp(instruction_i[27]),
    .a,.b,.roundingMode(rounding_i),.out(add_result),.exceptionFlags(add_flags));
  mulRecFN #(EXP,SIG) u_mul(.control(1'b1),.a,.b,.roundingMode(rounding_i),
    .out(mul_result),.exceptionFlags(mul_flags));
  mulAddRecFN #(EXP,SIG) u_fma(.control(1'b1),.op(fma_op),.a,.b,.c,
    .roundingMode(rounding_i),.out(fma_result),.exceptionFlags(fma_flags));
  recFNToFN #(EXP,SIG) u_add_out(.in(add_result),.out(add_ieee));
  recFNToFN #(EXP,SIG) u_mul_out(.in(mul_result),.out(mul_ieee));
  recFNToFN #(EXP,SIG) u_fma_out(.in(fma_result),.out(fma_ieee));
  assign integer_operand=instruction_i[21] ? a_i:
    (instruction_i[20]?{32'b0,a_i[31:0]}:{{32{a_i[31]}},a_i[31:0]});
  iNToRecFN #(64,EXP,SIG) u_from_int(.control(1'b1),.signedIn(!instruction_i[20]),
    .in(integer_operand),.roundingMode(rounding_i),.out(from_int_result),.exceptionFlags(from_int_flags));
  recFNToFN #(EXP,SIG) u_from_int_out(.in(from_int_result),.out(from_int_ieee));
  recFNToIN #(EXP,SIG,32) u_to_int32(.control(1'b1),.in(a),.roundingMode(rounding_i),
    .signedOut(!instruction_i[20]),.out(int32_result),.intExceptionFlags(int32_flags));
  recFNToIN #(EXP,SIG,64) u_to_int64(.control(1'b1),.in(a),.roundingMode(rounding_i),
    .signedOut(!instruction_i[20]),.out(int64_result),.intExceptionFlags(int64_flags));
  assign signaling_compare=instruction_i[14:12]!=2 && !instruction_i[14];
  compareRecFN #(EXP,SIG) u_compare(.a,.b,.signaling(signaling_compare),
    .lt(less),.eq(equal),.gt(greater),.unordered,.exceptionFlags(compare_flags));
  divSqrtRecFN_small #(EXP,SIG,0) u_divsqrt(.clock(clk_i),.nReset(rst_ni),
    .control(1'b1),.inReady(slow_ready_o),.inValid(slow_valid_i),
    .sqrtOp(instruction_i[30]),.a,.b,.roundingMode(rounding_i),
    .outValid(slow_result_valid_o),.sqrtOpOut(),.out(slow_result),.exceptionFlags(slow_flags_o));
  recFNToFN #(EXP,SIG) u_slow_out(.in(slow_result),.out(slow_data_o));
  always_comb begin
    a_nan=(&a_i[WIDTH-2-:EXP]) && (|a_i[SIG-2:0]);
    b_nan=(&b_i[WIDTH-2-:EXP]) && (|b_i[SIG-2:0]);
    a_snan=a_nan && !a_i[SIG-2];b_snan=b_nan && !b_i[SIG-2];
    a_zero=a_i[WIDTH-2:0]==0;b_zero=b_i[WIDTH-2:0]==0;
    classification=0;
    if(a_nan) classification[a_snan?8:9]=1;
    else if(&a_i[WIDTH-2-:EXP]) classification[a_i[WIDTH-1]?0:7]=1;
    else if(a_zero) classification[a_i[WIDTH-1]?3:4]=1;
    else if(a_i[WIDTH-2-:EXP]==0) classification[a_i[WIDTH-1]?2:5]=1;
    else classification[a_i[WIDTH-1]?1:6]=1;
    choose_max=instruction_i[12];
    if((a_nan && b_nan) || (instruction_i[13] && (a_nan || b_nan))) selected_minmax=QNAN;
    else if(a_nan) selected_minmax=b_i[WIDTH-1:0];
    else if(b_nan) selected_minmax=a_i[WIDTH-1:0];
    else if(a_zero && b_zero)
      selected_minmax={choose_max?(a_i[WIDTH-1]&b_i[WIDTH-1]):(a_i[WIDTH-1]|b_i[WIDTH-1]),{(WIDTH-1){1'b0}}};
    else selected_minmax=(choose_max?greater:less)?a_i[WIDTH-1:0]:b_i[WIDTH-1:0];
    fast_data_o=0;fast_flags_o=0;fast_supported_o=1;
    if(instruction_i[6:0] inside {7'h43,7'h47,7'h4b,7'h4f}) begin
      fast_data_o=64'(fma_ieee);fast_flags_o=fma_flags;
    end else case(instruction_i[31:27])
      0,1:begin fast_data_o=64'(add_ieee);fast_flags_o=add_flags;end
      2:begin fast_data_o=64'(mul_ieee);fast_flags_o=mul_flags;end
      4:begin
        fast_data_o=64'(a_i[WIDTH-1:0]);
        case(instruction_i[14:12])
          0:fast_data_o[WIDTH-1]=b_i[WIDTH-1];
          1:fast_data_o[WIDTH-1]=!b_i[WIDTH-1];
          2:fast_data_o[WIDTH-1]=a_i[WIDTH-1]^b_i[WIDTH-1];
          default:fast_supported_o=0;
        endcase
      end
      5:begin fast_data_o=64'(selected_minmax);fast_flags_o={a_snan|b_snan,4'b0};end
      20:begin
        case(instruction_i[14:12])
          0,4:fast_data_o=64'(less || equal);
          1,5:fast_data_o=64'(less);
          2:fast_data_o=64'(equal);
          default:fast_supported_o=0;
        endcase
        fast_flags_o=compare_flags;
      end
      24:begin
        if(instruction_i[21]) begin fast_data_o=int64_result;fast_flags_o={|int64_flags[2:1],3'b0,int64_flags[0]};end
        else begin fast_data_o={{32{int32_result[31]}},int32_result};fast_flags_o={|int32_flags[2:1],3'b0,int32_flags[0]};end
      end
      26:begin fast_data_o=64'(from_int_ieee);fast_flags_o=from_int_flags;end
      28:begin
        if(instruction_i[14:12]==1) fast_data_o={54'b0,classification};
        else fast_data_o=64'($signed(a_i[WIDTH-1:0]));
      end
      30:fast_data_o=64'(a_i[WIDTH-1:0]);
      default:fast_supported_o=0;
    endcase
  end
endmodule

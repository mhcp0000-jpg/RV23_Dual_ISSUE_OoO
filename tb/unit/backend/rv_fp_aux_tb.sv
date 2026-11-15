`timescale 1ns/1ps
module rv_fp_aux_tb;
  logic [383:0] vectors[65536];
  logic [63:0] operand,result,converted,modular;
  logic [31:0] round_s,fli_s;
  logic [63:0] round_d,fli_d;
  logic [4:0] flags,convert_flags,round_s_flags,round_d_flags;
  logic [1:0] source_format,destination_format;
  logic [2:0] rm;
  logic notify_nx;
  logic [3:0] kind;
  string vector_file;
  int count;
  rv_fp_convert cvt(.operand_i(operand),.source_format_i(source_format),
    .destination_format_i(destination_format),.rounding_i(rm),.result_o(converted),.flags_o(convert_flags));
  rv_fp_round_to_int #(.EXP(8),.SIG(24)) rs(.operand_i(operand[31:0]),.rounding_i(rm),
    .signal_inexact_i(notify_nx),.result_o(round_s),.flags_o(round_s_flags));
  rv_fp_round_to_int rd(.operand_i(operand),.rounding_i(rm),
    .signal_inexact_i(notify_nx),.result_o(round_d),.flags_o(round_d_flags));
  rv_fp_immediate #(.EXP(8),.SIG(24)) fs(.index_i(operand[4:0]),.value_o(fli_s));
  rv_fp_immediate fd(.index_i(operand[4:0]),.value_o(fli_d));
  rv_fp_cvtmod modword(.operand_i(operand),.result_o(modular));
  always_comb begin
    result=0;flags=0;
    case(kind)
      0:begin result=converted;flags=convert_flags;end
      1:begin result=destination_format==0?{32'hffffffff,round_s}:round_d;
        flags=destination_format==0?round_s_flags:round_d_flags;end
      2:result=destination_format==0?{32'hffffffff,fli_s}:fli_d;
      3:result=modular;
      default:begin end
    endcase
  end
  initial begin
    if(!$value$plusargs("vectors=%s",vector_file) || !$value$plusargs("count=%d",count))$fatal(1,"missing FP auxiliary vectors");
    $readmemh(vector_file,vectors);
    for(int i=0;i<count;i++) begin
      kind=vectors[i][383:380];destination_format=vectors[i][379:378];
      source_format=vectors[i][377:376];rm=vectors[i][375:373];notify_nx=vectors[i][372];
      operand=vectors[i][351:288];#1;
      if(result!==vectors[i][159:96] || flags!==vectors[i][95:91])
        $fatal(1,"FP aux vector%0d kind%0d src%0d dst%0d rm%0d operand%h result%h/%h expected%h/%h",
          i,kind,source_format,destination_format,rm,operand,result,flags,vectors[i][159:96],vectors[i][95:91]);
    end
    $display("PASS rv_fp_aux_tb vectors=%0d conversions/NaN-box/FROUND/FLI/FCVTMOD",count);$finish;
  end
endmodule

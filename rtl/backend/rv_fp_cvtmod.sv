// FCVTMOD.W.D data: truncate the unbounded integer, take low 32 bits, then
// sign extend. The ordinary FCVT.W.D/RTZ datapath supplies exception flags.
module rv_fp_cvtmod(input logic [63:0] operand_i,output logic [63:0] result_o);
  integer exponent,shift;
  logic [52:0] significand;
  logic [31:0] low_word;
  always_comb begin
    exponent=int'(operand_i[62:52])-1023;shift=exponent-52;
    significand={1'b1,operand_i[51:0]};low_word=0;
    if(operand_i[62:52]!=11'h7ff && exponent>=0) begin
      if(shift>=0 && shift<32) low_word=32'(significand<<shift);
      else if(shift<0) low_word=32'(significand>>(-shift));
      if(operand_i[63]) low_word=~low_word+1'b1;
    end
    result_o={{32{low_word[31]}},low_word};
  end
endmodule

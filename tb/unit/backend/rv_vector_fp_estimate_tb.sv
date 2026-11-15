`timescale 1ns/1ps
module rv_vector_fp_estimate_tb;
  logic [63:0] operand,result16,result32,result64,expected,result;
  logic reciprocal_sqrt;
  logic [2:0] rounding;
  logic [4:0] flags16,flags32,flags64,flags,expected_flags;
  int width,fd,n,count=0;
  string path;
  wire [15:0] data16;wire [31:0] data32;wire [63:0] data64;
  assign result16=64'(data16);assign result32=64'(data32);assign result64=data64;
  rv_vector_fp_estimate #(.EXP(5),.FRAC(10)) u_half(.operand_i(operand[15:0]),.reciprocal_sqrt_i(reciprocal_sqrt),
    .rounding_i(rounding),.result_o(data16),.flags_o(flags16));
  rv_vector_fp_estimate u_single(.operand_i(operand[31:0]),.reciprocal_sqrt_i(reciprocal_sqrt),
    .rounding_i(rounding),.result_o(data32),.flags_o(flags32));
  rv_vector_fp_estimate #(.EXP(11),.FRAC(52)) u_double(.operand_i(operand),.reciprocal_sqrt_i(reciprocal_sqrt),
    .rounding_i(rounding),.result_o(data64),.flags_o(flags64));
  initial begin
    if(!$value$plusargs("vectors=%s",path))$fatal(1,"missing vectors");fd=$fopen(path,"r");
    if(fd==0)$fatal(1,"cannot open vectors");
    while(!$feof(fd))begin
      n=$fscanf(fd,"%d %d %d %h %h %h\n",width,reciprocal_sqrt,rounding,operand,expected,expected_flags);
      if(n!=6)$fatal(1,"bad vector %0d",count);
      #1;result=width==16?result16:width==32?result32:result64;
      flags=width==16?flags16:width==32?flags32:flags64;
      if(result!==expected || flags!==expected_flags)
        $fatal(1,"estimate W%0d sqrt%0d rm%0d in%h got%h/%h expected%h/%h case%0d",
          width,reciprocal_sqrt,rounding,operand,result,flags,expected,expected_flags,count);
      count++;
    end
    $display("PASS rv_vector_fp_estimate_tb vectors=%0d",count);$finish;
  end
endmodule

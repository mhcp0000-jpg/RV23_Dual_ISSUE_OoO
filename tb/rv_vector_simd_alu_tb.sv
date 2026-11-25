module rv_vector_simd_alu_tb;
  import rv_vector_decode_pkg::*;
  vector_integer_operation_e operation;
  logic [1:0] sew,rounding,extension;
  logic [127:0] a,b,c,result,expected;
  logic [15:0] carry,saturated,expected_sat;
  int fd,fields,count=0,op_value;
  string path;
  rv_vector_simd_alu dut(.operation_i(operation),.sew_size_i(sew),.rounding_i(rounding),.extension_factor_i(extension),
    .a_i(a),.b_i(b),.c_i(c),.carry_i(carry),.result_o(result),.saturated_o(saturated));
  initial begin
    if(!$value$plusargs("vectors=%s",path))$fatal(1,"Missing SIMD arithmetic vectors");
    fd=$fopen(path,"r");if(!fd)$fatal(1,"Cannot open SIMD vectors");
    while(!$feof(fd))begin
      fields=$fscanf(fd,"%h %h %h %h %h %h %h %h %h %h\n",op_value,sew,rounding,extension,a,b,c,carry,expected,expected_sat);
      if(fields!=10)$fatal(1,"Invalid SIMD vector");
      operation=vector_integer_operation_e'(op_value);#1;
      if(result!==expected || saturated!==expected_sat)$fatal(1,"SIMD op=%0d sew=%0d result=%h/%h sat=%h/%h",op_value,sew,result,expected,saturated,expected_sat);
      count++;
    end
    $display("PASS rv_vector_simd_alu_tb cases=%0d",count);$finish;
  end
endmodule

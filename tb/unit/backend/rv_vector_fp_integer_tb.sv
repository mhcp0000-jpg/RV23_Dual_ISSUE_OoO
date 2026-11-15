`timescale 1ns/1ps
module rv_vector_fp_integer_tb;
  logic [63:0] operand,expected,result;
  logic fp_double,unsigned_integer,to_float;
  logic [1:0] integer_size;
  logic [2:0] rounding;
  logic [4:0] flags,expected_flags;
  string path;
  int fd,n,count=0;
  rv_vector_fp_integer dut(.operand_i(operand),.fp_double_i(fp_double),.integer_size_i(integer_size),
    .unsigned_i(unsigned_integer),.to_float_i(to_float),.rounding_i(rounding),.result_o(result),.flags_o(flags));
  initial begin
    if(!$value$plusargs("vectors=%s",path))$fatal(1,"missing vector data");fd=$fopen(path,"r");
    if(fd==0)$fatal(1,"cannot open vector data");
    while(!$feof(fd))begin
      n=$fscanf(fd,"%h %h %h %h %h %h %h %h\n",fp_double,integer_size,unsigned_integer,to_float,rounding,operand,expected,expected_flags);
      if(n!=8)$fatal(1,"bad vector %0d",count);#1;
      if(result!==expected || flags!==expected_flags)
        $fatal(1,"vector conversion #%0d D%0d iw%0d unsigned%0d tofloat%0d rm%0d input%h got%h/%h expected%h/%h",
          count,fp_double,8<<integer_size,unsigned_integer,to_float,rounding,operand,result,flags,expected,expected_flags);
      count++;
    end
    $display("PASS rv_vector_fp_integer_tb vectors=%0d",count);$finish;
  end
endmodule

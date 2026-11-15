`timescale 1ns/1ps
module rv_vector_integer_alu_tb #(
  parameter int WIDTH=32
);
  import rv_vector_decode_pkg::*;
  vector_integer_operation_e operation;
  logic [63:0] a,b,c,result,expected;
  logic carry,wide,sat,supported;
  logic [1:0] rm,ext;
  logic [7:0] op;
  logic expected_sat,expected_support;
  int fd,fields,count=0;
  string path;
  rv_vector_integer_alu #(.WIDTH(WIDTH)) dut(
    .operation_i(operation),.operand_a_i(a),.operand_b_i(b),.accumulator_i(c),
    .carry_i(carry),.wide_source_i(wide),.rounding_i(rm),.extension_factor_i(ext),
    .result_o(result),.saturated_o(sat),.supported_o(supported));
  initial begin
    if(!$value$plusargs("vectors=%s",path))$fatal(1,"missing vectors");
    fd=$fopen(path,"r");if(!fd)$fatal(1,"cannot open vectors");
    while(!$feof(fd)) begin
      fields=$fscanf(fd,"%h %h %h %h %h %h %h %h %h %h %h\n",
        op,a,b,c,carry,wide,rm,ext,expected,expected_sat,expected_support);
      if(fields!=11)$fatal(1,"bad vector %0d fields%0d",count,fields);
      operation=vector_integer_operation_e'(op);#1;
      if(supported!==expected_support || (supported && (result!==expected || sat!==expected_sat)))
        $fatal(1,"W%0d case%0d op%0d a%h b%h c%h carry%0d wide%0d rm%0d ext%0d result%h/%0d/%0d expected%h/%0d/%0d",
          WIDTH,count,op,a,b,c,carry,wide,rm,ext,result,sat,supported,expected,expected_sat,expected_support);
      count++;
    end
    $display("PASS rv_vector_integer_alu_tb W%0d vectors=%0d",WIDTH,count);$finish;
  end
endmodule

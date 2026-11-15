`timescale 1ns/1ps
module rv_vector_integer_engine_tb;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,request=0,ready,response,response_ready=0,exception,csr_write=0;
  logic [31:0] instruction=0;
  logic [63:0] a=0,b=0,result,csr_data=0,vl,vtype,vstart;
  logic [11:0] csr_address=0;
  logic [1:0] rm;
  logic sat,dirty;
  int fd,fields,count=0,kind;
  logic [63:0] expected;
  bit expected_exception;
  logic [1:0] expected_sat;
  logic [4:0] flags,expected_flags;
  logic [2:0] frm=0;
  logic fp_enabled=1;
  string path;
  rv_vector_engine dut(.clk_i(clk),.rst_ni(rst_n),.request_valid_i(request),.request_ready_o(ready),
    .instruction_i(instruction),.scalar_a_i(a),.scalar_b_i(b),.fp_state_enabled_i(fp_enabled),.frm_i(frm),
    .response_valid_o(response),.response_ready_i(response_ready),.response_flags_o(flags),
    .response_data_o(result),.response_exception_o(exception),.csr_write_i(csr_write),.csr_address_i(csr_address),.csr_data_i(csr_data),
    .vl_o(vl),.vtype_o(vtype),.vstart_o(vstart),.vxrm_o(rm),.vxsat_o(sat),.state_dirty_o(dirty));
  initial begin
    if(!$value$plusargs("vectors=%s",path))$fatal(1,"missing vectors");
    fd=$fopen(path,"r");if(!fd)$fatal(1,"cannot open vectors");
    repeat(3)@(negedge clk);rst_n=1;
    while(!$feof(fd))begin
      fields=$fscanf(fd,"%h %h %h %h %h %h %h %h %h %h\n",kind,instruction,a,b,expected,expected_exception,expected_sat,expected_flags,frm,fp_enabled);
      if(fields!=10)$fatal(1,"bad packet at %0d fields%0d",count,fields);
      if(kind==1)begin
        csr_address=instruction[11:0];csr_data=a;csr_write=1;
        @(negedge clk);csr_write=0;
      end else begin
        request=1;
        do @(posedge clk);while(!ready);
        @(negedge clk);request=0;wait(response);#1;
        if(exception!==expected_exception || (!exception && (result!==expected || flags!==expected_flags)) || (exception && flags!==0))
          $fatal(1,"vector owner case%0d insn%h result%h/%h/%0d expected%h/%h/%0d vl%0d type%h start%0d",
            count,instruction,result,flags,exception,expected,expected_flags,expected_exception,vl,vtype,vstart);
        repeat(2)@(negedge clk);
        response_ready=1;@(negedge clk);response_ready=0;
      end
      #1;if(expected_sat!=2 && sat!==expected_sat[0])$fatal(1,"vxsat mismatch case%0d",count);
      count++;@(negedge clk);
    end
    $display("PASS rv_vector_integer_engine_tb instruction packets=%0d",count);$finish;
  end
  initial begin #10000000;$fatal(1,"vector owner timeout");end
endmodule

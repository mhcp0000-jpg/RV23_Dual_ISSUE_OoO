`timescale 1ns/1ps
module rv_vector_fp_lane_tb;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,request=0,ready,response,response_ready=0,mask;
  logic [31:0] instruction;
  logic [1:0] sew;
  logic [2:0] frm;
  logic [63:0] a,b,c,result,expected;
  logic [4:0] flags,expected_flags;
  logic exception,expected_exception;
  int fd,n,count=0;
  string path;
  rv_vector_fp_lane dut(.clk_i(clk),.rst_ni(rst_n),.request_valid_i(request),.request_ready_o(ready),
    .instruction_i(instruction),.sew_size_i(sew),.frm_i(frm),.mask_i(mask),
    .operand_a_i(a),.operand_b_i(b),.operand_c_i(c),.response_valid_o(response),.response_ready_i(response_ready),
    .response_data_o(result),.response_flags_o(flags),.response_exception_o(exception));
  initial begin
    if(!$value$plusargs("vectors=%s",path))$fatal(1,"missing vectors");fd=$fopen(path,"r");
    if(fd==0)$fatal(1,"cannot open vectors");repeat(3)@(negedge clk);rst_n=1;
    while(!$feof(fd))begin
      n=$fscanf(fd,"%h %h %h %h %h %h %h %h %h %h\n",instruction,sew,frm,mask,a,b,c,expected,expected_flags,expected_exception);
      if(n!=10)$fatal(1,"bad vector %0d",count);
      request=1;do @(posedge clk);while(!ready);
      @(negedge clk);request=0;wait(response);#1;
      if(exception!==expected_exception || (!exception && (result!==expected || flags!==expected_flags)) || (exception && flags!==0))
        $fatal(1,"vector FP #%0d insn%h sew%0d rm%0d mask%0d a%h b%h c%h got%h/%h/%0d expected%h/%h/%0d",
          count,instruction,8<<sew,frm,mask,a,b,c,result,flags,exception,expected,expected_flags,expected_exception);
      if(count%17==0)repeat(3)@(negedge clk);
      @(negedge clk);response_ready=1;@(negedge clk);response_ready=0;count++;@(negedge clk);
    end
    $display("PASS rv_vector_fp_lane_tb vectors=%0d",count);$finish;
  end
  initial begin #100000000;$fatal(1,"vector FP timeout packet%0d insn%h lane_state%0d",count,instruction,dut.state_q);end
endmodule

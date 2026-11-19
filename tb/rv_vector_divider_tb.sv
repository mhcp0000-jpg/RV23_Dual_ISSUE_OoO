module rv_vector_divider_tb;
  logic clk=0,rst_n=0;
  always #5 clk=~clk;
  logic req=0,ready,valid,take=0,sign_op,rem_op;
  logic [1:0] sew;
  logic [63:0] a,b,result;
  int count=0;
  rv_vector_divider dut(.clk_i(clk),.rst_ni(rst_n),.request_valid_i(req),.request_ready_o(ready),
    .sew_size_i(sew),.signed_i(sign_op),.remainder_i(rem_op),.operand_a_i(a),.operand_b_i(b),
    .response_valid_o(valid),.response_ready_i(take),.result_o(result));
  task automatic run_case(input int size_value,input int op,input logic[63:0] av,bv);
    int cycles;
    logic [63:0] saved;
    @(negedge clk);sew=2'(size_value);sign_op=op<2;rem_op=op[0];a=av;b=bv;req=1;
    while(!ready)@(negedge clk);
    @(posedge clk);#1;
    @(negedge clk);req=0;sew=~sew;a=0;b='1;sign_op=~sign_op;rem_op=~rem_op;
    cycles=0;
    while(!valid)begin @(posedge clk);#1;cycles++;if(cycles>70)$fatal(1,"Missing vector divide result");end
    if(cycles!=68 || ready)$fatal(1,"Variable latency or overlapping owner: %0d",cycles);
    saved=result;
    repeat(3)begin @(negedge clk);if(!valid || result!==saved || ready)$fatal(1,"Unstable vector result");end
    $display("VDIV size=%0d op=%0d a=%016h b=%016h result=%016h cycles=%0d",size_value,op,av,bv,result,cycles);
    take=1;@(posedge clk);#1;@(negedge clk);take=0;
    if(valid || !ready)$fatal(1,"Vector divider did not release owner");
    count++;
  endtask
  initial begin
    repeat(4)@(negedge clk);rst_n=1;
    for(int size_value=0;size_value<4;size_value++)for(int op=0;op<4;op++)begin
      run_case(size_value,op,0,0);
      run_case(size_value,op,1,0);
      run_case(size_value,op,64'hffffffffffffffff,1);
      run_case(size_value,op,64'b1<<((8<<size_value)-1),'1);
      run_case(size_value,op,64'hfedcba9876543210,7);
      run_case(size_value,op,64'h1234567887654380,64'h8000000080000080);
      run_case(size_value,op,3,7);
      run_case(size_value,op,64'h7fffffffffffffff,3);
    end
    $display("PASS rv_vector_divider_tb cases=%0d",count);$finish;
  end
  initial begin #2000000;$fatal(1,"Vector divider watchdog");end
endmodule

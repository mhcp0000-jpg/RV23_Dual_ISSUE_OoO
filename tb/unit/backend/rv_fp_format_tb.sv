`timescale 1ns/1ps
module rv_fp_format_tb #(parameter int WIDTH=64);
  logic clk=0,rst=0;
  always #5 clk=~clk;
  logic [383:0] vectors[65536];
  logic [31:0] instruction;
  logic [63:0] a,b,c,result;
  logic [4:0] flags,slow_flags;
  logic supported,slow_start=0,slow_ready,slow_valid;
  logic [WIDTH-1:0] slow_data;
  logic [2:0] rm;
  string file_name;
  int count,checks=0;
  rv_fp_format #(.EXP(WIDTH==64?11:8),.SIG(WIDTH==64?53:24)) dut(
    .clk_i(clk),.rst_ni(rst),.instruction_i(instruction),.a_i(a),.b_i(b),.c_i(c),
    .rounding_i(rm),.fast_data_o(result),.fast_flags_o(flags),.fast_supported_o(supported),
    .slow_valid_i(slow_start),.slow_ready_o(slow_ready),.slow_result_valid_o(slow_valid),
    .slow_data_o(slow_data),.slow_flags_o(slow_flags));
  initial begin
    if(!$value$plusargs("vectors=%s",file_name) || !$value$plusargs("count=%d",count))$fatal(1,"missing FP vectors");
    $readmemh(file_name,vectors);
    instruction=0;a=0;b=0;c=0;rm=0;
    repeat(3) @(negedge clk);rst=1;
    for(int i=0;i<count;i++) begin
      @(negedge clk);instruction=vectors[i][383:352];a=vectors[i][351:288];
      b=vectors[i][287:224];c=vectors[i][223:160];rm=vectors[i][90:88];
      #1;
      if(vectors[i][87]) begin
        wait(slow_ready);@(negedge clk);slow_start=1;
        @(negedge clk);slow_start=0;wait(slow_valid);#1;
        if(64'(slow_data)!==vectors[i][159:96] || slow_flags!==vectors[i][95:91])
          $fatal(1,"FP%0d slow vector%0d insn%h rm%0d a%h b%h result%h/%h expected%h/%h",
            WIDTH,i,instruction,rm,a,b,slow_data,slow_flags,vectors[i][159:96],vectors[i][95:91]);
        @(negedge clk);
      end else if(!supported || result!==vectors[i][159:96] || flags!==vectors[i][95:91])
        $fatal(1,"FP%0d fast vector%0d insn%h rm%0d a%h b%h c%h result%h/%h expected%h/%h supported%0d",
          WIDTH,i,instruction,rm,a,b,c,result,flags,vectors[i][159:96],vectors[i][95:91],supported);
      checks++;
    end
    $display("PASS rv_fp_format_tb WIDTH=%0d exact_vectors=%0d",WIDTH,checks);$finish;
  end
  initial begin #1000000000;$fatal(1,"FP format timeout");end
endmodule

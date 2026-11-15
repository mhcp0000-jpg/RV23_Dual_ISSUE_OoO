`timescale 1ns/1ps
module rv_fpu_rva23_tb;
  import rv_ooo_pkg::*;
  logic clk=0,rst=0;
  always #5 clk=~clk;
  logic [383:0] vectors[65536];
  logic request=0,ready,result_valid,result_ready=0,exception_flag,flush=0,flush_all=0;
  logic [31:0] instruction=0;
  logic [63:0] a=0,b=0,c=0,data,tval;
  logic [2:0] rm=0,frm=0;
  logic [7:0] seqno=0,result_seq,flush_seq=0;
  logic [6:0] dst=0,result_dst;
  reg_class_e dst_class=REG_FP,result_class;
  logic result_dst_valid;
  logic [4:0] flags;
  exception_code_e cause;
  string vector_file;
  int count,checks=0;
  rv_fpu_rva23 dut(.clk_i(clk),.rst_ni(rst),.request_valid_i(request),.request_ready_o(ready),
    .instruction_i(instruction),.operand_a_i(a),.operand_b_i(b),.operand_c_i(c),
    .rounding_mode_i(rm),.frm_i(frm),.sequence_i(seqno),.destination_valid_i(1'b1),
    .destination_class_i(dst_class),.destination_phys_i(dst),
    .flush_valid_i(flush),.flush_all_i(flush_all),.flush_sequence_i(flush_seq),
    .result_valid_o(result_valid),.result_ready_i(result_ready),.result_sequence_o(result_seq),
    .result_destination_valid_o(result_dst_valid),.result_destination_class_o(result_class),
    .result_destination_phys_o(result_dst),.result_data_o(data),.result_fflags_o(flags),
    .result_exception_valid_o(exception_flag),.result_exception_cause_o(cause),.result_exception_tval_o(tval));
  task automatic send;
    wait(ready);@(negedge clk);request=1;
    do @(posedge clk);while(!ready);
    @(negedge clk);request=0;
  endtask
  task automatic consume(input logic[63:0] expected,input logic[4:0] expected_flags,input bit illegal=0);
    wait(result_valid);repeat(3) @(negedge clk);
    if(data!==expected || flags!==expected_flags || exception_flag!==illegal ||
       result_seq!==seqno || result_dst!==dst || result_class!==dst_class || !result_dst_valid ||
       (illegal && (cause!=EXC_ILLEGAL_INSTRUCTION || tval!==64'(instruction))))
      $fatal(1,"profile FP check%0d insn%h a%h b%h c%h data%h/%h expected%h/%h exc%0d expected%0d",
        checks,instruction,a,b,c,data,flags,expected,expected_flags,exception_flag,illegal);
    result_ready=1;@(negedge clk);result_ready=0;checks++;
  endtask
  initial begin
    if(!$value$plusargs("vectors=%s",vector_file) || !$value$plusargs("count=%d",count))$fatal(1,"missing profile FP vectors");
    $readmemh(vector_file,vectors);
    repeat(3) @(negedge clk);rst=1;
    for(int i=0;i<count;i++) begin
      instruction=vectors[i][383:352];a=vectors[i][351:288];b=vectors[i][287:224];c=vectors[i][223:160];
      rm=instruction[14:12];frm=vectors[i][90:88];
      dst_class=vectors[i][87]?REG_INT:REG_FP;dst=7'(32+i%48);seqno=8'(i);
      send();consume(vectors[i][159:96],vectors[i][95:91],vectors[i][86]);
    end
    // Killed slow operations must relinquish the divider and never leak a WB.
    instruction=32'h1a1001d3; // FDIV.D f3,f0,f1, RNE
    a=64'h3ff0000000000000;b=64'h4000000000000000;c=0;
    rm=0;frm=0;dst_class=REG_FP;seqno=2;dst=40;
    send();repeat(3) @(negedge clk);flush_seq=250;flush=1;
    @(negedge clk);flush=0;
    repeat(70) begin @(negedge clk);if(result_valid)$fatal(1,"killed FDIV leaked result");end
    // The next operation may reuse this transport with a different generation.
    seqno=3;send();consume(64'h3fe0000000000000,0);
    // A wrapped older/equal sequence survives a selective younger flush.
    seqno=250;send();repeat(3) @(negedge clk);flush_seq=2;flush=1;
    @(negedge clk);flush=0;consume(64'h3fe0000000000000,0);
    // Flush an already produced, backpressured result and then reuse again.
    seqno=8;send();wait(result_valid);@(negedge clk);flush_all=1;flush=1;
    @(negedge clk);flush=0;flush_all=0;
    if(result_valid)$fatal(1,"flushed FP result still valid");
    seqno=9;send();consume(64'h3fe0000000000000,0);
    $display("PASS rv_fpu_rva23_tb vectors=%0d checks=%0d boxing/metadata/backpressure/flush",count,checks);$finish;
  end
  initial begin #2000000000;$fatal(1,"RVA23 FP unit timeout");end
endmodule

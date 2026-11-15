`timescale 1ns/1ps
// Paired architectural vector owners: common instructions/configuration and
// different register/scalar data. Compare handshakes on every cycle.
module rv_vector_timing_tb;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,request=0,response_ready=0;
  logic [31:0] instruction=0;
  logic [1:0] ready,response,exception;
  logic [1:0][63:0] a=0,b=0;
  logic [63:0] scan_a0,scan_b0,scan_a1,scan_b1;
  int fd,logfd,fields,group_id,count=0,cycles,probes=0;
  string path,logpath;
  for(genvar lane=0;lane<2;lane++)begin:g_owner
    rv_vector_engine dut(.clk_i(clk),.rst_ni(rst_n),.request_valid_i(request),.request_ready_o(ready[lane]),
      .instruction_i(instruction),.scalar_a_i(a[lane]),.scalar_b_i(b[lane]),
      .response_valid_o(response[lane]),.response_ready_i(response_ready),.response_exception_o(exception[lane]),
      .csr_write_i(1'b0),.csr_address_i(12'b0),.csr_data_i(64'b0));
  end
  initial begin
    if(!$value$plusargs("vectors=%s",path) || !$value$plusargs("latencies=%s",logpath))$fatal(1,"missing timing files");
    fd=$fopen(path,"r");logfd=$fopen(logpath,"w");
    if(!fd || !logfd)$fatal(1,"cannot open timing files");
    $fwrite(logfd,"group,instruction,cycles,illegal\n");
    repeat(3)@(negedge clk);rst_n=1;
    while(!$feof(fd))begin
      // Standalone scan targets avoid a Verilator C++ lvalue bug for 64-bit
      // slices of packed multidimensional arrays.
      fields=$fscanf(fd,"%h %h %h %h %h %h\n",group_id,instruction,scan_a0,scan_b0,scan_a1,scan_b1);
      if(fields!=6)$fatal(1,"bad timing packet %0d",count);
      a[0]=scan_a0;b[0]=scan_b0;a[1]=scan_a1;b[1]=scan_b1;
      request=1;
      do begin
        @(posedge clk);
        if(ready[0]!==ready[1])$fatal(1,"data-dependent request ready packet%0d",count);
      end while(!ready[0]);
      @(negedge clk);request=0;cycles=0;
      while(!response[0])begin
        if(response[0]!==response[1])$fatal(1,"data-dependent completion packet%0d insn%h",count,instruction);
        @(negedge clk);cycles++;
      end
      if(response!==2'b11 || exception[0]!==exception[1])$fatal(1,"different timing/legality packet%0d",count);
      if(group_id!=0)begin
        $fwrite(logfd,"%0d,%08h,%0d,%0d\n",group_id,instruction,cycles,exception[0]);probes++;
      end
      repeat(2)@(negedge clk);
      response_ready=1;@(negedge clk);response_ready=0;
      count++;@(negedge clk);
    end
    $fclose(logfd);
    $display("PASS rv_vector_timing_tb packets=%0d paired_probes=%0d",count,probes);$finish;
  end
  initial begin #1000000000;$fatal(1,"vector timing timeout packet%0d insn%h",count,instruction);end
endmodule

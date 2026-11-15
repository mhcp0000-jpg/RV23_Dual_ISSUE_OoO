`timescale 1ns/1ps
module rv23_misaligned_head_tb;
  import rv_ooo_pkg::*;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,req=0,ready,rsp,rsp_ready=0;
  logic [63:0] address=0,operand=0,result,tval;
  logic [2:0] size=0;
  logic write_enable=0,unsign=0,floating=0,exception;
  logic [5:0] cause;
  privilege_e privilege=PRIV_M;
  logic [7:0][7:0] pmpcfg=0;
  logic [7:0][61:0] pmpaddr=0;
  logic mv,mr,mw,mrv=0,mrr;
  logic [31:0] ma;
  logic [63:0] md,mrd=0;
  logic [7:0] ms;
  byte unsigned memory[512];
  int ticks=0,accesses=0,checks=0;
  assign mr=!mrv && ticks%3!=0;
  rv23_misaligned_head #(.HAS_MMU(0)) dut(
    .clk_i(clk),.rst_ni(rst_n),.invalidate_i(1'b0),
    .request_valid_i(req),.request_ready_o(ready),.address_i(address),.operand_i(operand),
    .size_i(size),.write_i(write_enable),.unsigned_i(unsign),.floating_i(floating),.privilege_i(privilege),
    .mstatus_i(64'b0),.satp_i(64'b0),.menvcfg_i(64'b0),.senvcfg_i(64'b0),.pmpcfg_i(pmpcfg),.pmpaddr_i(pmpaddr),
    .response_valid_o(rsp),.response_ready_i(rsp_ready),.response_data_o(result),.response_tval_o(tval),
    .response_exception_o(exception),.response_cause_o(cause),
    .ptw_valid_o(),.ptw_device_o(),.ptw_ready_i(1'b0),.ptw_address_o(),
    .ptw_response_valid_i(1'b0),.ptw_response_ready_o(),.ptw_data_i(64'b0),.ptw_error_i(1'b0),
    .memory_valid_o(mv),.memory_ready_i(mr),.memory_write_o(mw),.memory_address_o(ma),
    .memory_data_o(md),.memory_strobe_o(ms),.memory_response_valid_i(mrv),.memory_response_ready_o(mrr),
    .memory_response_data_i(mrd),.memory_response_error_i(1'b0));
  always @(posedge clk) begin
    ticks<=ticks+1;
    if(mrv && mrr)mrv<=0;
    if(mv && mr) begin
      if(ma<32'h80000000 || ma>=32'h80000200)$fatal(1,"unexpected memory address %h",ma);
      accesses<=accesses+1;mrv<=1;
      for(int b=0;b<8;b++) begin
        mrd[b*8+:8]<=memory[{ma[8:3],3'b0}+b];
        if(mw && ms[b]) memory[{ma[8:3],3'b0}+b]<=md[b*8+:8];
      end
    end
  end
  task automatic transact(input logic[63:0] expected,input bit fault=0,
                          input logic[5:0] fault_cause=0,input logic[63:0] fault_address=0);
    @(negedge clk);req=1;
    do @(posedge clk);while(!ready);
    @(negedge clk);req=0;
    wait(rsp);#1;
    if(exception!==fault || (fault && (cause!==fault_cause || tval!==fault_address)) ||
       (!fault && !write_enable && result!==expected))
      $fatal(1,"assist addr%h size%0d write%0d result%h want%h fault%0d/%0d cause%0d tval%h want%h",
        address,size,write_enable,result,expected,exception,fault,cause,tval,fault_address);
    repeat(4)@(negedge clk);
    rsp_ready=1;@(negedge clk);rsp_ready=0;checks++;
  endtask
  initial begin
    logic [63:0] expected;
    int before_access;
    for(int b=0;b<512;b++)memory[b]=8'(b+128);
    repeat(3)@(negedge clk);rst_n=1;
    for(int s=1;s<=3;s++) for(int offset=1;offset<8;offset++) begin
      if(offset%(1<<s)==0)continue;
      address=64'h80000038+64'(offset);size=3'(s);write_enable=1;
      operand=64'h0123456789abcdef;floating=0;unsign=0;
      transact(0);
      for(int b=0;b<(1<<s);b++)
        if(memory[56+offset+b]!==operand[b*8+:8])$fatal(1,"store data mismatch");
      write_enable=0;
      for(int f=0;f<3;f++) begin
        floating=f==2;unsign=f==1;expected=0;
        for(int b=0;b<(1<<s);b++)expected[b*8+:8]=memory[56+offset+b];
        if(s==1)expected=floating?{48'hffffffffffff,expected[15:0]}:
          (unsign?{48'b0,expected[15:0]}:{{48{expected[15]}},expected[15:0]});
        if(s==2)expected=floating?{32'hffffffff,expected[31:0]}:
          (unsign?{32'b0,expected[31:0]}:{{32{expected[31]}},expected[31:0]});
        transact(expected);
      end
    end
    privilege=PRIV_S;pmpaddr[0]=62'(64'h80000040>>2);pmpcfg[0]=8'h0f;
    address=64'h8000003d;size=3;write_enable=1;before_access=accesses;
    transact(0,1,7,64'h80000040);
    if(accesses!=before_access)$fatal(1,"PMP denied split store had side effects");
    privilege=PRIV_M;
    address=64'h800ffffd;before_access=accesses;
    transact(0,1,7,64'h80100000);
    if(accesses!=before_access)$fatal(1,"end-of-SRAM split store had side effects");
    address=64'h02000001;write_enable=0;
    transact(0,1,5,address);
    if(accesses!=before_access)$fatal(1,"MMIO read escaped");
    $display("PASS rv23_misaligned_head_tb checks=%0d byte_accesses=%0d",checks,accesses);$finish;
  end
  initial begin #1000000;$fatal(1,"assist timeout");end
endmodule

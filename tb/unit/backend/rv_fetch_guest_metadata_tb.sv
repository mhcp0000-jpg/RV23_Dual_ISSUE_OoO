`timescale 1ns/1ps
module rv_fetch_guest_metadata_tb;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,fill=0,ready,redirect=0,implicit_access=0;
  logic [63:0] address=0,guest_address=0,redirect_pc=0;
  logic [127:0] data=0;
  logic [1:0] resp=0,valid,out_ready=0,fault,implicit_result;
  logic [5:0] cause=1;
  logic [1:0][63:0] pc,tval,gpa;
  logic [1:0][5:0] out_cause;
  int checks=0;
  rv_fetch_queue #(.XLEN(64),.PADDR_WIDTH(64),.RESET_VECTOR(64'h4000000e)) dut(
    .clk_i(clk),.rst_ni(rst_n),.fill_valid_i(fill),.fill_ready_o(ready),.fill_addr_i(address),
    .normal_fill_addr_i(64'b0),.normal_fill_valid_i(1'b0),.fill_id_i(4'b0),.fill_epoch_i(4'b0),
    .fill_data_i(data),.fill_resp_i(resp),.fill_fault_cause_i(cause),.fill_guest_address_i(guest_address),
    .fill_implicit_guest_access_i(implicit_access),.fill_pmp_allow_i(8'hff),
    .redirect_valid_i(redirect),.redirect_pc_i(redirect_pc),.new_epoch_i(4'b0),
    .out_valid_o(valid),.out_ready_i(out_ready),.out_pc_o(pc),.out_fault_o(fault),
    .out_fault_cause_o(out_cause),.out_fault_address_o(tval),.out_guest_address_o(gpa),.out_implicit_guest_access_o(implicit_result));
  task automatic send(input logic[63:0] va,input logic[127:0] payload,input bit error,
                       input logic[63:0] guest,input bit imp=0);
    @(negedge clk);address=va;data=payload;resp=error?2'd2:2'd0;cause=20;guest_address=guest;implicit_access=imp;fill=1;
    do @(posedge clk);while(!ready);
    @(negedge clk);fill=0;checks++;
  endtask
  task automatic check(input int lane,input logic[63:0] expected_pc,expected_va,expected_gpa,input bit imp=0);
    #1;if(!valid[lane] || !fault[lane] || out_cause[lane]!=20 || pc[lane]!=expected_pc ||
          tval[lane]!=expected_va || gpa[lane]!=expected_gpa || implicit_result[lane]!=imp)
      $fatal(1,"fetch guest lane%0d valid%0d fault%0d pc%h tval%h gpa%h implicit%0d",lane,valid[lane],fault[lane],pc[lane],tval[lane],gpa[lane],implicit_result[lane]);
    checks++;
  endtask
  task automatic consume;
    @(negedge clk);out_ready=1;@(negedge clk);out_ready=0;
  endtask
  initial begin
    repeat(3)@(negedge clk);rst_n=1;
    send(64'h40000000,128'h00130001000100010001000100010001,0,0);
    #1;if(valid[0])$fatal(1,"partial instruction became visible");
    send(64'h40000010,{8{16'h0001}},1,64'h10004000);
    repeat(4)begin check(0,64'h4000000e,64'h40000010,64'h10004000);@(negedge clk);end
    consume();check(0,64'h40000012,64'h40000012,64'h10004002);check(1,64'h40000014,64'h40000014,64'h10004004);
    @(negedge clk);redirect_pc=64'h4000001e;redirect=1;@(negedge clk);redirect=0;
    send(64'h40000010,128'h00130001000100010001000100010001,0,0);
    send(64'h40000020,{8{16'h0001}},1,64'h10002018,1);
    check(0,64'h4000001e,64'h40000020,64'h10002018,1);
    consume();check(0,64'h40000022,64'h40000022,64'h10002018,1);check(1,64'h40000024,64'h40000024,64'h10002018,1);
    $display("PASS rv_fetch_guest_metadata_tb checks=%0d cross-block parcels/GPA offsets/implicit-PTE/backpressure",checks);$finish;
  end
  initial begin #100000;$fatal(1,"fetch guest metadata timeout");end
endmodule

`timescale 1ns/1ps
module rv23_if_translate_tb;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,request=0,ready,response,response_ready=0,bus_valid,bus_ready=0,bus_response=0,bus_rsp_ready;
  logic [63:0] address=0;
  logic [3:0] id=0,epoch=0,rsp_id,rsp_epoch,bus_id,bus_epoch,returned_id=0,returned_epoch=0;
  logic [31:0] bus_address;
  logic [127:0] data=0,rsp_data;
  logic [1:0] resp=0,rsp_resp;
  logic [5:0] cause;
  int checks=0;
  rv23_if_translate dut(.clk_i(clk),.rst_ni(rst_n),.invalidate_i(1'b0),.halt_i(1'b0),
    .req_valid_i(request),.req_ready_o(ready),.req_address_i(address),.req_id_i(id),.req_epoch_i(epoch),
    .privilege_i(2'd3),.virtual_i(1'b0),.mxr_i(1'b0),.hs_mxr_i(1'b0),.pbmt_enable_i(1'b0),.guest_pbmt_enable_i(1'b0),
    .satp_i(64'b0),.vsatp_i(64'b0),.hgatp_i(64'b0),.rsp_valid_o(response),.rsp_ready_i(response_ready),
    .rsp_id_o(rsp_id),.rsp_epoch_o(rsp_epoch),.rsp_data_o(rsp_data),.rsp_resp_o(rsp_resp),.rsp_cause_o(cause),
    .bus_valid_o(bus_valid),.bus_ready_i(bus_ready),.bus_address_o(bus_address),.bus_id_o(bus_id),.bus_epoch_o(bus_epoch),
    .bus_rsp_valid_i(bus_response),.bus_rsp_ready_o(bus_rsp_ready),.bus_rsp_id_i(returned_id),.bus_rsp_epoch_i(returned_epoch),
    .bus_rsp_data_i(data),.bus_rsp_resp_i(resp),.mem_ready_i(1'b0),.mem_response_valid_i(1'b0),.mem_response_data_i(64'b0),.mem_response_error_i(1'b0));
  task automatic start(input logic[63:0] va,input logic[3:0] request_id,request_epoch);
    @(negedge clk);address=va;id=request_id;epoch=request_epoch;request=1;
    do @(posedge clk);while(!ready);
    @(negedge clk);request=0;
  endtask
  task automatic consume;
    repeat(4)@(negedge clk);response_ready=1;@(negedge clk);response_ready=0;bus_response=0;checks++;
  endtask
  initial begin
    repeat(3)@(negedge clk);rst_n=1;
    start(64'h80001000,4'ha,4'h7);wait(bus_valid);#1;
    if(bus_address!=32'h80001000 || bus_id!=10 || bus_epoch!=7)$fatal(1,"translated request metadata");
    repeat(3)@(negedge clk);bus_ready=1;@(negedge clk);bus_ready=0;
    returned_id=4'h9;returned_epoch=4'h2;data=128'h0123456789abcdef0011223344556677;bus_response=1;#1;
    if(!response || rsp_id!=9 || rsp_epoch!=2 || rsp_data!=data)$fatal(1,"external response was relabeled with saved metadata");
    consume();
    start(64'h100000000,4'h4,4'h8);wait(response);#1;
    if(bus_valid || rsp_id!=4 || rsp_epoch!=8 || rsp_resp!=2 || cause!=1)$fatal(1,"local IF fault must retain request metadata");
    consume();
    start(64'h80002000,4'h3,4'hc);wait(bus_valid);@(negedge clk);bus_ready=1;@(negedge clk);bus_ready=0;
    returned_id=3;returned_epoch=4'hb;bus_response=1;#1;
    if(rsp_epoch!=4'hb)$fatal(1,"stale external epoch hidden");consume();
    $display("PASS rv23_if_translate_tb checks=%0d actual/stale response identity and local fault ownership",checks);$finish;
  end
  initial begin #100000;$fatal(1,"IF translation protocol timeout");end
endmodule

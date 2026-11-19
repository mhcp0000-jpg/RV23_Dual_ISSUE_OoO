module rv23_head_cache_router_tb;
  import rv_soc_pkg::*;
  logic clk=0,rst_n=0;
  always #5 clk=~clk;
  rv_local_mem_if m[2](.clk_i(clk),.rst_ni(rst_n));
  rv_local_mem_if t[2](.clk_i(clk),.rst_ni(rst_n));
  logic [1:0] valid=0,ready,take=0,response;
  logic [1:0][5:0] ids;
  logic [1:0][5:0] response_ids;
  logic [1:0][31:0] address;
  logic [1:0][63:0] data,reply;
  logic head_cache=0,idle;
  logic [1:0] enabled=3;
  int cases_count=0,cycle=0,stream_accepts=0,stream_responses=0,first_accept,last_accept,first_response;
  bit streaming=0;
  function automatic logic[63:0] answer(input bit direct_value,input logic[31:0] addr_value,input logic[63:0] data_value);
    return (direct_value?64'hda00000000000000:64'hca00000000000000)^64'(addr_value)^data_value;
  endfunction
  for(genvar p=0;p<2;p++)begin:g_master
    assign m[p].req_valid=valid[p];assign ready[p]=m[p].req_ready;
    assign m[p].req_id=ids[p];assign m[p].req_addr=address[p];
    assign m[p].req_write=1;assign m[p].req_size=3;assign m[p].req_wdata=data[p];
    assign m[p].req_wstrb=8'hff;assign m[p].req_priv=PRIV_M;assign m[p].req_rob_seq=0;
    assign m[p].req_committed=1;assign m[p].req_device=0;assign m[p].rsp_ready=take[p];
    assign response[p]=m[p].rsp_valid;assign reply[p]=m[p].rsp_rdata;
    assign response_ids[p]=m[p].rsp_id;
  end
  for(genvar p=0;p<2;p++)begin:g_target
    logic occupied;
    logic [5:0] saved_id;
    logic [63:0] saved_data;
    assign t[p].req_ready=enabled[p] && (!occupied || t[p].rsp_ready);
    assign t[p].rsp_valid=occupied;assign t[p].rsp_id=saved_id;assign t[p].rsp_rdata=saved_data;
    assign t[p].rsp_resp=AXI_RESP_OKAY;assign t[p].rsp_replay=MEM_REPLAY_NONE;
    always_ff @(posedge clk)begin
      if(!rst_n)occupied<=0;
      else begin
        if(t[p].rsp_valid && t[p].rsp_ready)occupied<=0;
        if(t[p].req_valid && t[p].req_ready)begin
          occupied<=1;saved_id<=t[p].req_id;saved_data<=answer(p!=0,t[p].req_addr,t[p].req_wdata);
          if(!t[p].req_write || !t[p].req_committed || t[p].req_wstrb!=8'hff || t[p].req_size!=3 ||
             t[p].req_priv!=PRIV_M || t[p].req_device || t[p].req_rob_seq!=0)$fatal(1,"Lost request metadata");
        end
      end
    end
  end
  rv23_head_cache_router dut(.clk_i(clk),.rst_ni(rst_n),.head_cache_i(head_cache),.idle_o(idle),
    .scalar_bus(m[0]),.head_bus(m[1]),.cache_bus(t[0]),.direct_bus(t[1]));
  always @(posedge clk)if(rst_n)begin
    cycle++;
    if(streaming)begin
      if(valid[0] && ready[0])begin
        if(stream_accepts==0)first_accept=cycle;
        stream_accepts++;last_accept=cycle;
      end
      if(response[0] && take[0])begin
        if(stream_responses==0)first_response=cycle;
        if(m[0].rsp_id!=6'(stream_responses) ||
           reply[0]!==answer(0,32'h80000000+32'(stream_responses*8),64'(stream_responses)))
          $fatal(1,"Scalar pipeline response was reordered");
        stream_responses++;
      end
    end
  end
  task automatic transfer(input int port_id,input int identity,input bit direct_value);
    logic [63:0] expected;
    @(negedge clk);ids[port_id]=6'(identity);address[port_id]=32'h80001000+32'(identity*8);
    data[port_id]=64'h123456789abcdef0^64'(identity);valid[port_id]=1;
    expected=answer(direct_value,address[port_id],data[port_id]);
    do @(posedge clk);while(!ready[port_id]);
    @(negedge clk);valid[port_id]=0;
    wait(response[port_id]);
    repeat(3)begin @(negedge clk);if(!response[port_id] || reply[port_id]!==expected || response_ids[port_id]!=6'(identity))
      $fatal(1,"Wrong owner/route/held response");end
    take[port_id]=1;@(posedge clk);@(negedge clk);take[port_id]=0;cases_count++;
  endtask
  initial begin
    ids=0;address=0;data=0;
    repeat(4)@(negedge clk);rst_n=1;
    streaming=1;take[0]=1;
    for(int n=0;n<20;n++)begin
      @(negedge clk);valid[0]=1;ids[0]=6'(n);address[0]=32'h80000000+32'(n*8);data[0]=64'(n);
      @(posedge clk);if(!ready[0])$fatal(1,"Inserted scalar hit bubble");
    end
    @(negedge clk);valid[0]=0;
    wait(stream_responses==20);@(negedge clk);streaming=0;take[0]=0;
    if(stream_accepts!=20 || last_accept-first_accept!=19 || first_response-first_accept!=1)
      $fatal(1,"Scalar hit latency/throughput changed");
    enabled[0]=0;head_cache=1;
    fork
      transfer(0,32,0);
      begin wait(t[0].req_valid);transfer(1,33,0);end
      begin repeat(6)@(negedge clk);enabled[0]=1;end
    join
    enabled[0]=0;head_cache=1;
    fork
      transfer(1,34,0);
      begin wait(valid[1]);repeat(3)@(negedge clk);head_cache=0;enabled[0]=1;end
    join
    enabled[1]=0;head_cache=0;
    fork
      transfer(1,35,1);
      transfer(0,36,0);
      begin repeat(10)@(negedge clk);enabled[1]=1;end
    join
    for(int n=0;n<20;n++)begin
      head_cache=n[0];
      fork transfer(0,37+n,0);transfer(1,37+n,!n[0]);join
    end
    @(negedge clk);if(!idle || cases_count!=45)$fatal(1,"Router did not drain");
    $display("PASS rv23_head_cache_router_tb cases=%0d stream=20 span=%0d latency=%0d",
      cases_count+20,last_accept-first_accept,first_response-first_accept);$finish;
  end
  initial begin #200000;$fatal(1,"Router watchdog");end
endmodule

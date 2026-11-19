`timescale 1ns/1ps
module rv23_cache_burst_tb #(parameter bit BURST=1);
  import rv_soc_pkg::*;
  logic clk_i=0,rst_ni=0,invalidate=0,snoop=0,refill,idle,bridge_idle;
  logic [31:0] snoop_addr=0;
  always #5 clk_i=~clk_i;
  rv_local_mem_if cpu(.clk_i,.rst_ni),other(.clk_i,.rst_ni),mem(.clk_i,.rst_ni);
  rv_axi4_if axi(.clk_i,.rst_ni);
  rv23_cache cache(.clk_i,.rst_ni,.invalidate_i(invalidate),
    .snoop_valid_i(snoop),.snoop_addr_i(snoop_addr),.snoop_wdata_i(64'hface),
    .snoop_wstrb_i(8'hff),.idle_o(idle),.refill_o(refill),.cpu,.cpu_b(other),.mem);
  rv_local_to_axi_bridge #(.CACHE_BURST(BURST),.AXI_PROGRESS_TIMEOUT_CYCLES(32)) bridge(
    .clk_i,.rst_ni,.refill_i(refill),.idle_o(bridge_idle),.local_bus(mem),.axi_m(axi));
  assign other.req_valid=0;assign other.req_id=0;assign other.req_addr=0;
  assign other.req_write=0;assign other.req_size=3;assign other.req_wdata=0;
  assign other.req_wstrb=0;assign other.req_priv=PRIV_M;assign other.req_rob_seq=0;
  assign other.req_committed=0;assign other.req_device=0;assign other.rsp_ready=1;
  function automatic logic [63:0] pattern(input logic [31:0] addr);
    return 64'h9876543200000000 | {32'b0,addr};
  endfunction
  integer cycles=0,ars=0,rs=0,aws=0,checks=0;
  integer fault_beat=-1,wrong_id_beat=-1,last_mode=0;
  logic allow_ar=1,allow_r=1,reading=0,writing=0,bvalid=0;
  logic [31:0] raddr;
  logic [3:0] rid,bid;
  integer beat=0,length=0,delay_q=0;
  assign axi.ar_ready=allow_ar && !reading;
  assign axi.r_valid=reading && allow_r && delay_q==0;
  assign axi.r_id=rid ^ (beat==wrong_id_beat ? 4'd1:4'd0);
  assign axi.r_data=pattern(raddr+32'(beat*8));
  assign axi.r_resp=beat==fault_beat ? AXI_RESP_SLVERR:AXI_RESP_OKAY;
  assign axi.r_last=last_mode==1 ? beat==2 : last_mode==2 ? beat==length+1 : beat==length;
  assign axi.aw_ready=!writing && !bvalid;
  assign axi.w_ready=writing;
  assign axi.b_valid=bvalid;assign axi.b_id=bid;assign axi.b_resp=AXI_RESP_OKAY;
  always @(posedge clk_i) if(rst_ni) begin
    cycles<=cycles+1;
    if(axi.ar_valid && axi.ar_ready) begin
      if(axi.ar_size!=3 || axi.ar_burst!=1 ||
         axi.ar_len!=(BURST && refill ? 7:0)) $fatal(1,"AR shape");
      reading<=1;raddr<=axi.ar_addr;rid<=axi.ar_id;length<=int'(axi.ar_len);
      beat<=0;delay_q<=2;ars<=ars+1;
    end else if(delay_q>0) delay_q<=delay_q-1;
    if(axi.r_valid && axi.r_ready) begin
      rs<=rs+1;beat<=beat+1;delay_q<=2;
      if(axi.r_last) reading<=0;
    end
    if(axi.aw_valid && axi.aw_ready) begin
      if(axi.aw_len!=0) $fatal(1,"Burst write");
      writing<=1;bid<=axi.aw_id;aws<=aws+1;
    end
    if(axi.w_valid && axi.w_ready) begin
      if(!axi.w_last) $fatal(1,"Write LAST");
      writing<=0;bvalid<=1;
    end
    if(axi.b_valid && axi.b_ready) bvalid<=0;
  end
  task automatic access(input logic [31:0] addr,input bit wr=0,
                        input bit device=0,input bit error=0);
    @(negedge clk_i);cpu.req_valid=1;cpu.req_addr=addr;cpu.req_write=wr;
    cpu.req_committed=wr;cpu.req_device=device;cpu.rsp_ready=0;
    do @(posedge clk_i);while(!cpu.req_ready);
    @(negedge clk_i);cpu.req_valid=0;
    do @(negedge clk_i);while(!cpu.rsp_valid);
    repeat(4) begin
      if(cpu.rsp_id!=37 || cpu.rsp_resp!=(error ? AXI_RESP_SLVERR:AXI_RESP_OKAY) ||
         (!wr && !error && cpu.rsp_rdata!=pattern(addr)))
        $fatal(1,"Response addr=%h data=%h code=%h",addr,cpu.rsp_rdata,cpu.rsp_resp);
      @(negedge clk_i);
    end
    cpu.rsp_ready=1;@(negedge clk_i);cpu.rsp_ready=0;checks++;
  endtask
  task automatic wait_idle;
    do @(negedge clk_i);while(!bridge_idle || !idle);
  endtask
  task automatic flush;
    wait_idle();invalidate=1;@(negedge clk_i);invalidate=0;
  endtask
  integer start_cycles,start_ars,start_rs,cold_cycles;
  initial begin
    cpu.req_valid=0;cpu.req_id=37;cpu.req_addr=0;cpu.req_write=0;cpu.req_size=3;
    cpu.req_wdata=64'h1234;cpu.req_wstrb=8'hff;cpu.req_priv=PRIV_M;
    cpu.req_rob_seq=0;cpu.req_committed=0;cpu.req_device=0;cpu.rsp_ready=0;
    repeat(4) @(negedge clk_i);rst_ni=1;
    start_cycles=cycles;access(32'h80000028);wait_idle();cold_cycles=cycles-start_cycles;
    if(ars!=(BURST ? 1:8) || rs!=8) $fatal(1,"Cold refill count %d/%d",ars,rs);
    start_ars=ars;
    for(int i=0;i<8;i++) access(32'h80000000+32'(i*8));
    if(ars!=start_ars) $fatal(1,"Resident word missed");
    access(32'h80001000,1);if(aws!=1) $fatal(1,"WT completion");
    start_ars=ars;access(32'h10000000,0,1);wait_idle();
    if(ars-start_ars!=1) $fatal(1,"MMIO allocated");
    access(32'h10000000,0,1);wait_idle();
    if(ars-start_ars!=2) $fatal(1,"MMIO hit");
    if(BURST) begin
      // Errors at every beat must fault the entire cache fill, then retry cleanly.
      for(int f=0;f<8;f++) begin
        flush();fault_beat=f;access(32'h80002000,0,0,1);wait_idle();
        fault_beat=-1;start_ars=ars;access(32'h80002000);wait_idle();
        if(ars-start_ars!=1) $fatal(1,"Fault installed a tag");
      end
      flush();wrong_id_beat=3;access(32'h80003000,0,0,1);wait_idle();wrong_id_beat=-1;
      for(int m=1;m<=2;m++) begin
        flush();last_mode=m;access(32'h80004000,0,0,1);wait_idle();last_mode=0;
      end
      // Invalidate or snoop during a fill: return data, never install that tag.
      for(int s=0;s<2;s++) begin
        flush();start_ars=ars;
        fork
          access(32'h80005000);
          begin
            wait(reading && beat==2);@(negedge clk_i);
            if(s==0) invalidate=1;else begin snoop=1;snoop_addr=32'h80005000;end
            @(negedge clk_i);invalidate=0;snoop=0;
          end
        join
        wait_idle();access(32'h80005000);wait_idle();
        if(ars-start_ars!=2) $fatal(1,"Killed fill installed tag");
      end
      // Timeout while AR is stalled must preserve AR and prevent false idle.
      flush();allow_ar=0;
      access(32'h80006000,0,0,1);
      repeat(5) begin
        @(negedge clk_i);
        if(bridge_idle || !axi.ar_valid || axi.ar_addr!=32'h80006000 || axi.ar_len!=7)
          $fatal(1,"Timed-out AR lost ownership");
      end
      allow_ar=1;wait_idle();
      // Timeout after accepted AR drains its late burst before accepting a new fill.
      flush();allow_r=0;access(32'h80007000,0,0,1);
      if(bridge_idle || mem.req_ready) $fatal(1,"Early idle during late R");
      allow_r=1;wait_idle();access(32'h80007000);wait_idle();
    end
    $display("PASS rv23_cache_burst_tb burst=%0d cold_cycles=%0d checks=%0d ar=%0d r=%0d",BURST,cold_cycles,checks,ars,rs);
    $finish;
  end
  initial begin #2000000;$fatal(1,"Timeout");end
endmodule

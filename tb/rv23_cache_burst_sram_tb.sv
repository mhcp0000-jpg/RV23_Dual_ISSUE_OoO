`timescale 1ns/1ps
module rv23_cache_burst_sram_tb #(parameter bit BURST=1);
  import rv_soc_pkg::*;
  logic clk_i=0,rst_ni=0,invalidate=0,refill,idle,bridge_idle,snoop;
  logic [31:0] snoop_addr;
  logic [63:0] snoop_data;
  logic [7:0] snoop_strb;
  always #5 clk_i=~clk_i;
  rv_local_mem_if cpu(.clk_i,.rst_ni),other(.clk_i,.rst_ni),mem(.clk_i,.rst_ni),sram(.clk_i,.rst_ni);
  rv_axi4_if axi(.clk_i,.rst_ni);
  rv23_cache cache(.clk_i,.rst_ni,.invalidate_i(invalidate),
    .snoop_valid_i(snoop),.snoop_addr_i(snoop_addr),.snoop_wdata_i(snoop_data),
    .snoop_wstrb_i(snoop_strb),.idle_o(idle),.refill_o(refill),.cpu,.cpu_b(other),.mem);
  rv_local_to_axi_bridge #(.CACHE_BURST(BURST)) bridge(
    .clk_i,.rst_ni,.refill_i(refill),.idle_o(bridge_idle),.local_bus(mem),.axi_m(axi));
  rv_axi_to_local_bridge #(.TARGET_BASE_ADDR(32'h80000000),.TARGET_SIZE_KB(1024)) inbound(
    .clk_i,.rst_ni,.axi_s(axi),.local_bus(sram));
  rv23_sram ram(.clk_i,.rst_ni,.bus(sram),.write_snoop_o(snoop),
    .write_snoop_addr_o(snoop_addr),.write_snoop_data_o(snoop_data),.write_snoop_strb_o(snoop_strb));
  assign other.req_valid=0;assign other.req_id=0;assign other.req_addr=0;
  assign other.req_write=0;assign other.req_size=3;assign other.req_wdata=0;
  assign other.req_wstrb=0;assign other.req_priv=PRIV_M;assign other.req_rob_seq=0;
  assign other.req_committed=0;assign other.req_device=0;assign other.rsp_ready=1;
  integer cycles=0,ars=0,rs=0;
  always @(posedge clk_i) if(rst_ni) begin
    cycles<=cycles+1;
    if(axi.ar_valid && axi.ar_ready) begin
      ars<=ars+1;
      if(axi.ar_len!=(BURST ? 7:0)) $fatal(1,"Refill ARLEN");
    end
    if(axi.r_valid && axi.r_ready) rs<=rs+1;
  end
  function automatic logic [63:0] pattern(input logic [31:0] addr);
    return 64'h1234567800000000 | {32'b0,addr};
  endfunction
  task automatic access(input logic [31:0] addr,input bit wr=0,input bit updated=0);
    @(negedge clk_i);cpu.req_valid=1;cpu.req_addr=addr;cpu.req_write=wr;
    cpu.req_committed=wr;cpu.req_wdata=pattern(addr) ^ (updated ? 64'hfeedbabe:64'd0);cpu.rsp_ready=0;
    do @(posedge clk_i);while(!cpu.req_ready);
    @(negedge clk_i);cpu.req_valid=0;
    do @(negedge clk_i);while(!cpu.rsp_valid);
    if(cpu.rsp_id!=37 || cpu.rsp_resp!=AXI_RESP_OKAY ||
       (!wr && cpu.rsp_rdata!=(pattern(addr) ^ (updated ? 64'hfeedbabe:64'd0))))
      $fatal(1,"SRAM response addr=%h data=%h",addr,cpu.rsp_rdata);
    repeat(3) @(negedge clk_i);
    cpu.rsp_ready=1;@(negedge clk_i);cpu.rsp_ready=0;
  endtask
  integer start_cycles,cold_cycles,start_ars;
  initial begin
    cpu.req_valid=0;cpu.req_id=37;cpu.req_addr=0;cpu.req_write=0;cpu.req_size=3;
    cpu.req_wdata=0;cpu.req_wstrb=8'hff;cpu.req_priv=PRIV_M;
    cpu.req_rob_seq=0;cpu.req_committed=0;cpu.req_device=0;cpu.rsp_ready=0;
    repeat(4) @(negedge clk_i);rst_ni=1;
    // Populate the real SRAM through committed write-through transactions.
    for(int i=0;i<32*8;i++) access(32'h80000000+32'(i*8),1);
    start_cycles=cycles;
    for(int i=0;i<32;i++) access(32'h80000028+32'(i*64));
    cold_cycles=cycles-start_cycles;
    if(ars!=32*(BURST ? 1:8) || rs!=256) $fatal(1,"SRAM refill count");
    start_ars=ars;
    for(int i=0;i<32*8;i++) access(32'h80000000+32'(i*8));
    if(ars!=start_ars) $fatal(1,"SRAM resident miss");
    // A resident write-through snoop must keep the updated resident word usable.
    access(32'h80000010,1,1);access(32'h80000010,0,1);
    if(ars!=start_ars) $fatal(1,"SRAM snoop evicted line");
    $display("PASS rv23_cache_burst_sram_tb burst=%0d cold_cycles=%0d ar=%0d r=%0d",BURST,cold_cycles,ars,rs);
    $finish;
  end
  initial begin #2000000;$fatal(1,"SRAM timeout");end
endmodule

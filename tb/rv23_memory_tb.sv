`timescale 1ns/1ps
module rv23_memory_tb;
  import rv_soc_pkg::*;
  logic clk_i=0, rst_ni=0;
  always #5 clk_i=~clk_i;
  logic [2:0] req_valid,req_ready,rsp_ready,rsp_valid;
  logic [2:0][5:0] rsp_id;
  logic [2:0][63:0] rsp_rdata;
  logic [2:0][1:0] rsp_resp;
  logic [2:0][5:0] req_id;
  logic [2:0][31:0] req_addr;
  logic [2:0][0:0] req_write;
  logic [2:0][2:0] req_size;
  logic [2:0][63:0] req_wdata;
  logic [2:0][7:0] req_wstrb;
  logic [2:0][1:0] req_priv;
  logic [2:0][7:0] req_rob_seq;
  logic [2:0][0:0] req_committed;
  logic [2:0][0:0] req_device;
  rv_local_mem_if a (.clk_i,.rst_ni);
  rv_local_mem_if b (.clk_i,.rst_ni);
  rv_local_mem_if debug_local (.clk_i,.rst_ni);
  rv_local_mem_if d_cpu (.clk_i,.rst_ni);
  rv_local_mem_if d_mem (.clk_i,.rst_ni);
  rv_local_mem_if i_cpu (.clk_i,.rst_ni);
  rv_local_mem_if i_cpu_hi (.clk_i,.rst_ni);
  rv_local_mem_if i_mem (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) i_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) d_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) debug_axi (.clk_i,.rst_ni);
  logic snoop,msip,mtip,meip;
  logic [31:0] snoop_addr;
  logic [63:0] snoop_data;
  logic [7:0] snoop_strb;
  logic [63:0] mtime_value;
  localparam int PLIC_IDS = 8;
  localparam int TEST_IRQ = PLIC_IDS-1;
  logic [PLIC_IDS-1:1] irq;
  logic invalidate_i,if_valid,if_ready,if_rsp_valid,if_rsp_ready;
  logic [31:0] if_addr;
  logic [3:0] if_id,if_epoch,if_rid,if_repoch;
  logic [127:0] if_data;
  logic [1:0] if_resp;
  integer d_reads=0,i_reads=0,snoops=0,checks=0;
  integer edge_number=0;
  integer accept_edge[0:2],first_response_edge[0:2];
  integer if_accept_edge,if_first_response_edge;
  bit [2:0] measuring=0;
  bit if_measuring=0;
  always @(posedge clk_i) begin
    edge_number<=edge_number+1;
    if(rst_ni) begin
      for(int p=0;p<3;p++) if(req_valid[p] && req_ready[p]) begin
        accept_edge[p]=edge_number;measuring[p]=1;
      end
      if(if_valid && if_ready) begin if_accept_edge=edge_number;if_measuring=1;end
    end
  end
  always @(negedge clk_i) if(rst_ni) begin
    for(int p=0;p<3;p++) if(measuring[p] && rsp_valid[p]) begin
      first_response_edge[p]=edge_number;measuring[p]=0;
    end
    if(if_measuring && if_rsp_valid) begin if_first_response_edge=edge_number;if_measuring=0;end
  end
  always @(posedge clk_i) if (rst_ni) begin
    if(d_axi.ar_valid && d_axi.ar_ready) d_reads<=d_reads+1;
    if(i_axi.ar_valid && i_axi.ar_ready) i_reads<=i_reads+1;
    if(snoop) snoops<=snoops+1;
  end
  assign a.req_id = req_id[0];
  assign a.req_addr = req_addr[0];
  assign a.req_write = req_write[0];
  assign a.req_size = req_size[0];
  assign a.req_wdata = req_wdata[0];
  assign a.req_wstrb = req_wstrb[0];
  assign a.req_priv = rv_soc_pkg::privilege_e'(req_priv[0]);
  assign a.req_rob_seq = req_rob_seq[0];
  assign a.req_committed = req_committed[0];
  assign a.req_device = req_device[0];
  assign a.req_valid = req_valid[0];
  assign req_ready[0] = a.req_ready;
  assign a.rsp_ready = rsp_ready[0];
  assign rsp_valid[0] = a.rsp_valid;
  assign rsp_id[0] = a.rsp_id;
  assign rsp_rdata[0] = a.rsp_rdata;
  assign rsp_resp[0] = a.rsp_resp;
  assign b.req_id = req_id[1];
  assign b.req_addr = req_addr[1];
  assign b.req_write = req_write[1];
  assign b.req_size = req_size[1];
  assign b.req_wdata = req_wdata[1];
  assign b.req_wstrb = req_wstrb[1];
  assign b.req_priv = rv_soc_pkg::privilege_e'(req_priv[1]);
  assign b.req_rob_seq = req_rob_seq[1];
  assign b.req_committed = req_committed[1];
  assign b.req_device = req_device[1];
  assign b.req_valid = req_valid[1];
  assign req_ready[1] = b.req_ready;
  assign b.rsp_ready = rsp_ready[1];
  assign rsp_valid[1] = b.rsp_valid;
  assign rsp_id[1] = b.rsp_id;
  assign rsp_rdata[1] = b.rsp_rdata;
  assign rsp_resp[1] = b.rsp_resp;
  assign debug_local.req_id = req_id[2];
  assign debug_local.req_addr = req_addr[2];
  assign debug_local.req_write = req_write[2];
  assign debug_local.req_size = req_size[2];
  assign debug_local.req_wdata = req_wdata[2];
  assign debug_local.req_wstrb = req_wstrb[2];
  assign debug_local.req_priv = rv_soc_pkg::privilege_e'(req_priv[2]);
  assign debug_local.req_rob_seq = req_rob_seq[2];
  assign debug_local.req_committed = req_committed[2];
  assign debug_local.req_device = req_device[2];
  assign debug_local.req_valid = req_valid[2];
  assign req_ready[2] = debug_local.req_ready;
  assign debug_local.rsp_ready = rsp_ready[2];
  assign rsp_valid[2] = debug_local.rsp_valid;
  assign rsp_id[2] = debug_local.rsp_id;
  assign rsp_rdata[2] = debug_local.rsp_rdata;
  assign rsp_resp[2] = debug_local.rsp_resp;
  rv23_cache dc (.clk_i,.rst_ni,.invalidate_i(1'b0),
    .snoop_valid_i(snoop),.snoop_addr_i(snoop_addr),.snoop_wdata_i(snoop_data),.snoop_wstrb_i(snoop_strb),
    .idle_o(),.cpu(a),.cpu_b(b),.mem(d_mem));
  rv23_cache #(.READ_ONLY(1)) ic (.clk_i,.rst_ni,
    .invalidate_i(invalidate_i),.snoop_valid_i(snoop),.snoop_addr_i(snoop_addr),
    .snoop_wdata_i(snoop_data),.snoop_wstrb_i(snoop_strb),
    .idle_o(),.cpu(i_cpu),.cpu_b(i_cpu_hi),.mem(i_mem));
  rv23_if_adapter ifa (.clk_i,.rst_ni,.halt_i(1'b0),.req_valid_i(if_valid),.req_ready_o(if_ready),
    .req_addr_i(if_addr),.req_id_i(if_id),.req_epoch_i(if_epoch),
    .rsp_valid_o(if_rsp_valid),.rsp_ready_i(if_rsp_ready),
    .rsp_id_o(if_rid),.rsp_epoch_o(if_repoch),.rsp_data_o(if_data),
    .rsp_resp_o(if_resp),.quiescent_o(),.bus(i_cpu),.bus_hi(i_cpu_hi));
  rv_local_to_axi_bridge db (.clk_i,.rst_ni,.local_bus(d_mem),.axi_m(d_axi));
  rv_local_to_axi_bridge #(.IS_INSTRUCTION(1)) ib (
    .clk_i,.rst_ni,.local_bus(i_mem),.axi_m(i_axi));
  rv_local_to_axi_bridge hb (.clk_i,.rst_ni,.local_bus(debug_local),.axi_m(debug_axi));
  rv23_system_bus #(.PLIC_NUM_SOURCES(PLIC_IDS)) sys (.clk_i,.rst_ni,.external_irq_i(irq),
    .i_axi_s(i_axi),.d_axi_s(d_axi),.debug_axi_s(debug_axi),
    .write_snoop_o(snoop),.write_snoop_addr_o(snoop_addr),.msip_o(msip),.mtip_o(mtip),.meip_o(meip),
    .write_snoop_data_o(snoop_data),.write_snoop_strb_o(snoop_strb),
    .mtime_o(mtime_value),.host_event_ready_i(1'b1),.host_boot_entry_o(),
    .host_boot_flags_o(),.host_event_valid_o(),.host_event_kind_o(),.host_event_data_o());
  task automatic access_mem(input int p,input bit wr,input logic [31:0] addr,
    input logic [63:0] val,input logic [7:0] strb,input logic [2:0] size,
    input logic [1:0] expected_code,output logic [63:0] result);
    logic [63:0] saved;
    @(negedge clk_i);
    req_valid[p]=1;req_id[p]=6'(p+17);req_addr[p]=addr;req_write[p]=wr;
    req_wdata[p]=val;req_wstrb[p]=strb;req_size[p]=size;
    req_committed[p]=wr;req_device[p]=0;req_priv[p]=3;req_rob_seq[p]=8'(checks);
    do @(posedge clk_i); while(!req_ready[p]);
    @(negedge clk_i);req_valid[p]=0;
    do @(negedge clk_i); while(!rsp_valid[p]);
    saved=rsp_rdata[p];
    if(rsp_resp[p]!==expected_code || rsp_id[p]!==6'(p+17))
      $fatal(1,"Bad response port=%0d address=%h code=%h id=%h",p,addr,rsp_resp[p],rsp_id[p]);
    // Every response is held under backpressure for three complete cycles.
    repeat(3) begin
      @(negedge clk_i);
      if(!rsp_valid[p] || rsp_rdata[p]!==saved || rsp_resp[p]!==expected_code)
        $fatal(1,"Unstable memory response");
    end
    result=saved;rsp_ready[p]=1;
    @(negedge clk_i);rsp_ready[p]=0;checks=checks+1;
  endtask
  task automatic fetch(input logic [31:0] addr,input logic [127:0] expected,
    input logic [1:0] code);
    @(negedge clk_i);if_valid=1;if_addr=addr;if_id=9;if_epoch=11;
    do @(posedge clk_i);while(!if_ready);
    @(negedge clk_i);if_valid=0;
    do @(negedge clk_i);while(!if_rsp_valid);
    repeat(3) begin
      if(if_resp!==code || if_rid!==9 || if_repoch!==11 ||
          (code==0 && if_data!==expected))
        $fatal(1,"Bad/stalled instruction response addr=%h data=%h code=%h",addr,if_data,if_resp);
      @(negedge clk_i);
    end
    if_rsp_ready=1;@(negedge clk_i);if_rsp_ready=0;checks=checks+1;
  endtask
  task automatic stream_fetch;
    // A warmed line must deliver one complete 128-bit response per clock,
    // including a new request on the previous response's acceptance edge.
    @(negedge clk_i);if_rsp_ready=1;
    for(int n=0;n<8;n++) begin
      if_valid=1;if_addr=32'h80000000+32'((n%4)*16);if_id=4'(n);if_epoch=11;
      @(posedge clk_i);
      if(!if_ready) $fatal(1,"Warm fetch throughput bubble");
      if(n>0 && (!if_rsp_valid || if_rid!=4'(n-1) || if_repoch!=11 || if_resp!=0 ||
          if_data!={64'h101+64'(((n-1)%4)*2),64'h100+64'(((n-1)%4)*2)}))
        $fatal(1,"Pipelined 128-bit fetch pair/ownership");
      @(negedge clk_i);
    end
    if_valid=0;@(posedge clk_i);
    if(!if_rsp_valid || if_rid!=7 || if_data!={64'h107,64'h106})
      $fatal(1,"Last pipelined fetch response");
    @(negedge clk_i);if_rsp_ready=0;checks+=8;
  endtask
  logic [63:0] value,v0,v1;
  logic [63:0] reference_words [0:2047];
  int unsigned random_state=1;
  function automatic int unsigned next_random();
    random_state=random_state^(random_state<<13);
    random_state=random_state^(random_state>>17);
    random_state=random_state^(random_state<<5);
    return random_state;
  endfunction
  task automatic random_scoreboard;
    int unsigned random_value,word_number,region,selected_port,transfer_size,lane,index;
    logic [31:0] address;
    logic [63:0] write_value,actual;
    logic [7:0] mask;
    bit write_access;
    void'($value$plusargs("seed=%d",random_state));
    if(random_state==0) $fatal(1,"Random seed cannot be zero");
    for(int n=0;n<2048;n++) begin
      reference_words[n]=64'hb00b000000000000+64'(n)*64'h102030405;
      address=(n<1024?32'h80000000:32'h80008000)+32'((n%1024)*8);
      access_mem(2,1,address,reference_words[n],8'hff,3,0,actual);
    end
    for(int transaction=0;transaction<1024;transaction++) begin
      random_value=next_random();word_number=random_value%1024;
      region=(random_value>>12)&1;index=region*1024+word_number;
      selected_port=next_random()%3;transfer_size=next_random()%4;
      lane=(next_random()%8)&~((1<<transfer_size)-1);
      write_access=(next_random()%3)==0;
      address=(region==0?32'h80000000:32'h80008000)+32'(word_number*8+lane);
      write_value={next_random(),next_random()};
      mask=8'(((1<<(1<<transfer_size))-1)<<lane);
      access_mem(int'(selected_port),write_access,address,write_value,mask,
        3'(transfer_size),0,actual);
      if(write_access) begin
        for(int byte_number=0;byte_number<8;byte_number++)
          if(mask[byte_number]) reference_words[index][8*byte_number+:8]=write_value[8*byte_number+:8];
      end else if(actual!==reference_words[index])
        $fatal(1,"Random scoreboard seed=%0d tx=%0d port=%0d addr=%h got=%h expected=%h",
          random_state,transaction,selected_port,address,actual,reference_words[index]);
      if(transaction%32==0)
        fetch({address[31:4],4'b0},{reference_words[index|1],reference_words[index&~1]},0);
    end
    $display("RANDOM MEMORY PASS transactions=1024, initialized_words=2048");
  endtask
  int before_reads;
  initial begin
    req_valid=0;rsp_ready=0;req_id=0;req_addr=0;req_write=0;req_size=0;
    req_wdata=0;req_wstrb=0;req_priv=0;req_rob_seq=0;req_committed=0;req_device=0;
    if_valid=0;if_rsp_ready=0;if_addr=0;if_id=0;if_epoch=0;irq=0;invalidate_i=0;
    repeat(4) @(negedge clk_i);rst_ni=1;
    for(int n=0;n<8;n++) access_mem(2,1,32'h8000_0000+32'(n*8),64'h100+n,8'hff,3,0,value);
    // Miss fills eight beats; another word of the same line is a hit.
    before_reads=d_reads;
    access_mem(0,0,32'h8000_0000,0,0,3,0,value);
    if(value!==64'h100 || d_reads-before_reads!=8) $fatal(1,"D-cache miss/fill");
    before_reads=d_reads;
    access_mem(1,0,32'h8000_0038,0,0,3,0,value);
    if(value!==64'h107 || d_reads!=before_reads) $fatal(1,"D-cache hit");
    before_reads=i_reads;
    fetch(32'h8000_0000,{64'h101,64'h100},0);
    if(i_reads-before_reads!=8) $fatal(1,"I-cache miss");
    before_reads=i_reads;
    fetch(32'h8000_0010,{64'h103,64'h102},0);
    if(i_reads!=before_reads) $fatal(1,"I-cache hit");
    if(if_first_response_edge-if_accept_edge!=1) $fatal(1,"I-cache hit is not one cycle");
    stream_fetch();
    fork
      access_mem(0,0,32'h80000000,0,0,3,0,v0);
      access_mem(1,0,32'h80000008,0,0,3,0,v1);
    join
    if(v0!==64'h100 || v1!==64'h101 || accept_edge[0]!=accept_edge[1] ||
       first_response_edge[0]-accept_edge[0]!=1 || first_response_edge[1]-accept_edge[1]!=1)
      $fatal(1,"Different-bank parallel one-cycle reads");
    fork
      access_mem(0,0,32'h80000000,0,0,3,0,v0);
      access_mem(1,0,32'h80000010,0,0,3,0,v1);
    join
    if(v0!==64'h100 || v1!==64'h102 ||
       !((accept_edge[0]-accept_edge[1]==1) || (accept_edge[1]-accept_edge[0]==1)))
      $fatal(1,"Same-bank arbitration/held response ownership");
    access_mem(2,1,32'h80000608,64'habcd,8'hff,3,0,value);
    access_mem(1,0,32'h80000608,0,0,3,0,value);
    if(value!==64'habcd) $fatal(1,"Same-line write/read probe setup");
    fork
      access_mem(0,1,32'h80000600,64'h9876,8'hff,3,0,v0);
      begin
        wait(dc.state_q!=dc.IDLE && dc.write_q);
        access_mem(1,0,32'h80000608,0,0,3,0,v1);
      end
    join
    if(v1!==64'habcd || first_response_edge[1]-accept_edge[1]!=1 ||
       accept_edge[1]>=first_response_edge[0])
      $fatal(1,"Pending write blocked another word of the same line");
    $display("BANKED HIT PASS I128=1cycle D64=1cycle dual-bank parallel same-bank fair hit-under-write");
    // Both CPU stores and debug writes leave unrelated lines resident, even
    // when the written address has the same cache index and a different tag.
    access_mem(0,1,32'h80008000,64'h7654,8'hff,3,0,value);
    access_mem(2,1,32'h80008008,64'habcd,8'hff,3,0,value);
    before_reads=i_reads;
    fetch(32'h80000000,{64'h101,64'h100},0);
    if(i_reads!=before_reads) $fatal(1,"Unrelated store discarded instructions");
    before_reads=d_reads;
    access_mem(0,0,32'h80000000,0,0,3,0,value);
    if(value!==64'h100 || d_reads!=before_reads) $fatal(1,"Alias store discarded unrelated D tag");
    // Byte lane write-through and invalidation of both caches.
    access_mem(0,1,32'h8000_0001,64'h0000_0000_0000_aa00,8'h02,0,0,value);
    access_mem(2,0,32'h8000_0000,0,0,3,0,value);
    if(value!==64'haa00) $fatal(1,"Write-through/byte mask");
    fetch(32'h8000_0000,{64'h101,64'haa00},0);
    access_mem(1,0,32'h8000_0000,0,0,3,0,value);
    if(value!==64'haa00) $fatal(1,"Stale D-cache after write");
    access_mem(2,1,32'h8000_0000,64'hbeef,8'hff,3,0,value);
    access_mem(0,0,32'h8000_0000,0,0,3,0,value);
    if(value!==64'hbeef) $fatal(1,"Debug write snoop");
    fetch(32'h8000_0000,{64'h101,64'hbeef},0);
    @(negedge clk_i);invalidate_i=1;@(negedge clk_i);invalidate_i=0;
    before_reads=i_reads;
    fetch(32'h8000_0000,{64'h101,64'hbeef},0);
    if(i_reads-before_reads!=8) $fatal(1,"FENCE.I invalidate");
    // Invalidate on the final I-refill beat: the waiting upper half must
    // refill rather than observe a line installed after FENCE.I.
    for(int n=0;n<8;n++) access_mem(2,1,32'h80000800+32'(n*8),64'h500+64'(n),8'hff,3,0,value);
    before_reads=i_reads;
    fork
      fetch(32'h80000800,{64'h501,64'h500},0);
      begin
        wait(ic.state_q==ic.WAIT_MEM && ic.beat_q==7 && i_mem.rsp_valid);
        @(negedge clk_i);invalidate_i=1;@(negedge clk_i);invalidate_i=0;
      end
    join
    if(i_reads-before_reads!=16) $fatal(1,"Final-beat FENCE.I installed an old line");
    // A physical code write after the requested word was read invalidates the
    // whole snapshot. The old offered lower half is stable, then later fetches
    // must return the new code from the upper half's replacement fill.
    for(int n=0;n<8;n++) access_mem(2,1,32'h80000840+32'(n*8),64'h600+64'(n),8'hff,3,0,value);
    before_reads=i_reads;
    fork
      fetch(32'h80000840,{64'h601,64'h600},0);
      begin
        wait(ic.state_q==ic.WAIT_MEM && ic.beat_q==2);
        access_mem(2,1,32'h80000840,64'hdead,8'hff,3,0,value);
      end
    join
    if(i_reads-before_reads!=16) $fatal(1,"I snoop failed to cancel a refill");
    fetch(32'h80000840,{64'h601,64'hdead},0);
    fork
      fetch(32'h80000840,{64'h601,64'hdead},0);
      begin wait(if_rsp_valid);@(negedge clk_i);invalidate_i=1;@(negedge clk_i);invalidate_i=0;end
    join
    before_reads=i_reads;
    fetch(32'h80000840,{64'h601,64'hdead},0);
    if(i_reads-before_reads!=8) $fatal(1,"Held I response retained invalidated tag");
    $display("I PAIR RACES PASS final-beat FENCE.I, code snoop/refill, held response");
    // A debug write can overtake later beats of an active CPU refill. The
    // returned word may precede or follow that write; the next read must see it.
    access_mem(2,1,32'h80000400,64'h1122,8'hff,3,0,value);
    fork
      access_mem(0,0,32'h80000400,0,0,3,0,v0);
      begin
        wait(dc.state_q==dc.WAIT_MEM && dc.beat_q==2);
        access_mem(2,1,32'h80000400,64'h3344,8'hff,3,0,v1);
      end
    join
    if(v0!==64'h1122 && v0!==64'h3344) $fatal(1,"Racing refill response data");
    before_reads=d_reads;
    access_mem(1,0,32'h80000400,0,0,3,0,value);
    if(value!==64'h3344 || d_reads-before_reads!=8) $fatal(1,"Debug/refill installed stale data");
    // Zero byte enables cause no memory change and must not invalidate a line.
    before_reads=d_reads;
    access_mem(2,1,32'h80000400,64'hffff,8'h00,3,0,value);
    access_mem(0,0,32'h80000400,0,0,3,0,value);
    if(value!==64'h3344 || d_reads!=before_reads) $fatal(1,"Zero-mask write affected cache");
    before_reads=d_reads;
    fork
      access_mem(0,0,32'h80000400,0,0,3,0,v0);
      access_mem(2,1,32'h80000401,64'haa00,8'h02,0,0,v1);
    join
    if(v0!==64'h3344 && v0!==64'haa44) $fatal(1,"Resident snoop/read race");
    access_mem(1,0,32'h80000400,0,0,3,0,value);
    if(value!==64'haa44 || d_reads!=before_reads) $fatal(1,"Resident byte snoop did not merge");
    $display("SYSTEM SNOOP PASS CPU/debug alias retention, racing refill, zero byte mask");
    // Same index, different tag; last valid SRAM line, and upper-bound hole.
    access_mem(2,1,32'h8000_8000,64'hcafe,8'hff,3,0,value);
    access_mem(0,0,32'h8000_8000,0,0,3,0,value);
    if(value!==64'hcafe) $fatal(1,"Replacement data");
    before_reads=d_reads;
    access_mem(1,0,32'h8000_0000,0,0,3,0,value);
    if(value!==64'hbeef || d_reads-before_reads!=8) $fatal(1,"Replacement tag");
    access_mem(2,1,32'h800f_fff8,64'h1234,8'hff,3,0,value);
    access_mem(0,0,32'h800f_fff8,0,0,3,0,value);
    if(value!==64'h1234) $fatal(1,"1MiB SRAM boundary");
    access_mem(0,0,32'h8010_0000,0,0,3,3,value);
    access_mem(1,0,32'h8000_0001,0,0,3,2,value);
    fetch(32'h0c00_0000,0,3); // Never issue instruction reads to MMIO.
    // Both LSU ports simultaneously pending; responses must return to owner.
    fork
      access_mem(0,0,32'h8000_0000,0,0,3,0,v0);
      access_mem(1,0,32'h8000_8000,0,0,3,0,v1);
    join
    if(v0!==64'hbeef || v1!==64'hcafe) $fatal(1,"Dual LSU arbitration");
    // A held write response belongs to its CPU slot even when the engine
    // accepts the other port's write and changes its current owner/ID.
    fork
      access_mem(0,1,32'h80000700,64'h12345678,8'hff,3,0,v0);
      access_mem(1,1,32'h80000708,64'habcd4321,8'hff,3,0,v1);
    join
    access_mem(1,0,32'h80000700,0,0,3,0,v0);
    access_mem(0,0,32'h80000708,0,0,3,0,v1);
    if(v0!==64'h12345678 || v1!==64'habcd4321) $fatal(1,"Dual write response ownership/data");
    $display("WRITE RESPONSE OWNERSHIP PASS dual-port held completion and SRAM data");
    access_mem(0,1,32'h0200_0000,1,8'h0f,2,0,value);
    if(!msip) $fatal(1,"CLINT MSIP not wired");
    access_mem(1,0,32'h0200_0000,0,0,2,0,value);
    if(value[31:0]!==1) $fatal(1,"CLINT read");
    access_mem(0,1,32'h0200_0000,0,8'h0f,2,0,value);
    if(msip) $fatal(1,"CLINT MSIP clear");
    access_mem(0,1,32'h0200_4000,0,8'h0f,2,0,value);
    access_mem(0,1,32'h0200_4004,0,8'hf0,2,0,value);
    if(!mtip) $fatal(1,"CLINT timer not wired");
    access_mem(0,1,32'h0200_4004,64'hffff_ffff_0000_0000,8'hf0,2,0,value);
    if(mtip) $fatal(1,"CLINT timer deassert");
    // Exercise the highest implemented ID of a non-default PLIC instance.
    access_mem(0,1,32'h0c00_0000+4*TEST_IRQ,64'h0000_0003_0000_0000,8'hf0,2,0,value);
    access_mem(0,1,32'h0c00_2000,64'd1<<TEST_IRQ,8'h0f,2,0,value);
    access_mem(0,1,32'h0c20_0000,0,8'h0f,2,0,value);
    @(negedge clk_i);irq[TEST_IRQ]=1;repeat(6) @(negedge clk_i);
    if(!meip) $fatal(1,"PLIC external interrupt not wired");
    access_mem(0,0,32'h0c20_0004,0,0,2,0,value);
    if(value[63:32]!==32'(TEST_IRQ)) $fatal(1,"PLIC claim");
    @(negedge clk_i);irq[TEST_IRQ]=0;repeat(5) @(negedge clk_i);
    access_mem(0,1,32'h0c20_0004,64'(TEST_IRQ)<<32,8'hf0,2,0,value);
    if(meip) $fatal(1,"PLIC complete");
    // Reset invalidates cache metadata without clearing the shared SRAM.
    @(negedge clk_i);rst_ni=0;repeat(3) @(negedge clk_i);rst_ni=1;
    before_reads=d_reads;
    access_mem(0,0,32'h8000_0000,0,0,3,0,value);
    if(value!==64'hbeef || d_reads-before_reads!=8) $fatal(1,"Reset persistence");
    if($test$plusargs("random_mem")) random_scoreboard();
    $display("PASS rv23_memory_tb checks=%0d d_reads=%0d i_reads=%0d snoops=%0d",checks,d_reads,i_reads,snoops);
    $finish;
  end
  initial begin #2000000; $fatal(1,"Memory subsystem watchdog"); end
endmodule

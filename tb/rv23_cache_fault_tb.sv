`timescale 1ns/1ps
module rv23_cache_fault_tb #(parameter bit QUEUE_WRITES=0);
  import rv_soc_pkg::*;
  logic clk_i=0,rst_ni=0,invalidate=0,allow_request=1,read_fault=0,write_fault=0;
  logic snoop=0,allow_response=1;
  logic [31:0] snoop_addr=0;
  always #5 clk_i=~clk_i;
  rv_local_mem_if cpu (.clk_i,.rst_ni);
  rv_local_mem_if mem (.clk_i,.rst_ni);
  rv_local_mem_if unused_cpu (.clk_i,.rst_ni);
  assign unused_cpu.req_valid=0;assign unused_cpu.req_id=0;assign unused_cpu.req_addr=0;
  assign unused_cpu.req_write=0;assign unused_cpu.req_size=3;
  assign unused_cpu.req_wdata=0;assign unused_cpu.req_wstrb=0;
  assign unused_cpu.req_priv=PRIV_M;assign unused_cpu.req_rob_seq=0;
  assign unused_cpu.req_committed=0;assign unused_cpu.req_device=0;assign unused_cpu.rsp_ready=1;
  rv23_cache #(.QUEUE_WRITES(QUEUE_WRITES)) dut (.clk_i,.rst_ni,.invalidate_i(invalidate),
    .snoop_valid_i(snoop),.snoop_addr_i(snoop_addr),.snoop_wdata_i(pattern(snoop_addr)),.snoop_wstrb_i(8'hff),
    .idle_o(),.cpu,.cpu_b(unused_cpu),.mem);
  integer requests=0,checks=0;
  logic response_valid;
  logic [5:0] response_id;
  logic [63:0] response_data;
  axi_resp_e response_code;
  function automatic logic [63:0] pattern(input logic [31:0] addr);
    return 64'h1234_0000 + {32'b0,addr[31:3],3'b0};
  endfunction
  assign mem.req_ready = allow_request && !response_valid && rst_ni;
  assign mem.rsp_valid = response_valid && allow_response;
  assign mem.rsp_id = response_id;
  assign mem.rsp_rdata = response_data;
  assign mem.rsp_resp = response_code;
  assign mem.rsp_replay = MEM_REPLAY_NONE;
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      response_valid<=0;response_id<=0;response_data<=0;response_code<=AXI_RESP_OKAY;
    end else begin
      if(mem.rsp_valid && mem.rsp_ready) response_valid<=0;
      if(mem.req_valid && mem.req_ready) begin
        requests<=requests+1;
        response_valid<=1;response_id<=mem.req_id;
        response_data<=pattern(mem.req_addr);
        response_code<=((read_fault && !mem.req_write && mem.req_addr[5:3]==3) ||
                       (write_fault && mem.req_write)) ? AXI_RESP_SLVERR : AXI_RESP_OKAY;
      end
    end
  end
  task automatic access_cache(input logic [31:0] addr,input bit write_access,
      input bit device,input logic [1:0] expected);
    @(negedge clk_i);cpu.req_valid=1;cpu.req_addr=addr;cpu.req_write=write_access;
    cpu.req_device=device;cpu.req_committed=write_access;
    do @(posedge clk_i);while(!cpu.req_ready);
    @(negedge clk_i);cpu.req_valid=0;
    do @(negedge clk_i);while(!cpu.rsp_valid);
    repeat(4) begin
      if(cpu.rsp_resp!==expected || cpu.rsp_id!==6'd37 ||
         (!write_access && expected==0 && cpu.rsp_rdata!==pattern(addr)))
        $fatal(1,"Cache fault contract addr=%h data=%h code=%h",addr,cpu.rsp_rdata,cpu.rsp_resp);
      @(negedge clk_i);
    end
    cpu.rsp_ready=1;@(negedge clk_i);cpu.rsp_ready=0;checks++;
  endtask
  task automatic response_ready_contract;
    integer count_before;
    count_before=requests;
    @(negedge clk_i);allow_response=0;cpu.rsp_ready=1;
    cpu.req_valid=1;cpu.req_addr=32'h80006000;cpu.req_write=1;cpu.req_committed=1;
    do @(posedge clk_i);while(!cpu.req_ready);
    @(negedge clk_i);cpu.req_valid=0;
    repeat(4) begin
      if(cpu.rsp_valid) $fatal(1,"Ready CPU received an early write completion");
      @(negedge clk_i);
    end
    allow_response=1;
    #1;if(!cpu.rsp_valid || cpu.rsp_id!==37 || cpu.rsp_resp!==AXI_RESP_OKAY)
      $fatal(1,"Ready CPU lost bus completion");
    @(negedge clk_i);
    repeat(4) begin
      if(cpu.rsp_valid || dut.busy_q[0]) $fatal(1,"Ready CPU saw duplicate completion or remained busy");
      @(negedge clk_i);
    end
    if(requests-count_before!=1) $fatal(1,"Ready CPU write duplicated");
    cpu.rsp_ready=0;cpu.req_write=0;cpu.req_committed=0;checks++;
  endtask
  integer before_count;
  // Check the actual acceptance edge, not just a final throughput number.
  // CPU payload changes after acceptance must not affect a stalled bus offer.
  task automatic launch_contract(input bit stalled,input bit writing,input bit device);
    logic [31:0] address;
    integer count_before;
    address=device ? 32'h02000080:32'h800070b8;
    count_before=requests;
    @(negedge clk_i);allow_request=!stalled;allow_response=0;
    cpu.req_valid=1;cpu.req_addr=address;cpu.req_write=writing;
    cpu.req_device=device;cpu.req_committed=writing;cpu.req_id=19;
    cpu.req_size=2;cpu.req_wdata=64'h8911223344556677;cpu.req_wstrb=8'hf0;
    cpu.req_priv=PRIV_U;cpu.req_rob_seq=83;
    @(posedge clk_i);
    if(!cpu.req_ready || !mem.req_valid || mem.req_ready!==!stalled)
      $fatal(1,"Cache launch inserted an acceptance bubble");
    if(mem.req_addr!==(device || writing ? address:{address[31:6],6'b0}) ||
       mem.req_size!==(device || writing ? 3'd2:3'd3) || mem.req_write!==writing ||
       mem.req_id!==19 || mem.req_wdata!==64'h8911223344556677 || mem.req_wstrb!==8'hf0 ||
       mem.req_priv!==PRIV_U || mem.req_rob_seq!==83 ||
       mem.req_committed!==writing || mem.req_device!==device)
      $fatal(1,"Cache launch payload corrupted");
    @(negedge clk_i);cpu.req_valid=0;cpu.req_addr=32'h90000000;cpu.req_id=2;
    cpu.req_write=0;cpu.req_committed=0;cpu.req_device=0;cpu.req_size=0;
    cpu.req_wdata=0;cpu.req_wstrb=0;cpu.req_priv=PRIV_M;cpu.req_rob_seq=0;
    if(stalled) begin
      repeat(4) begin
        if(!mem.req_valid || mem.req_addr!==(device || writing ? address:{address[31:6],6'b0}) ||
           mem.req_id!==19 || mem.req_wdata!==64'h8911223344556677 || mem.req_wstrb!==8'hf0 ||
           mem.req_priv!==PRIV_U || mem.req_rob_seq!==83 || mem.req_write!==writing ||
           mem.req_size!==(device || writing ? 3'd2:3'd3) ||
           mem.req_committed!==writing || mem.req_device!==device)
          $fatal(1,"Stalled cache launch lost captured ownership/payload");
        if(cpu.rsp_valid) $fatal(1,"Cache completed before bus request acceptance");
        @(negedge clk_i);
      end
      allow_request=1;@(negedge clk_i);
    end
    repeat(4) begin
      if(cpu.rsp_valid) $fatal(1,"Cache completed before bus response");
      @(negedge clk_i);
    end
    allow_response=1;
    #1;if((device || writing) && !cpu.rsp_valid)
      $fatal(1,"Cache inserted a stage after registered bus response");
    do @(negedge clk_i);while(!cpu.rsp_valid);
    repeat(3) begin
      if(cpu.rsp_id!==19 || cpu.rsp_resp!==AXI_RESP_OKAY || cpu.rsp_rdata!==pattern(address))
        $fatal(1,"Cache launch response lost ID/data");
      @(negedge clk_i);
    end
    if(requests-count_before!=(device || writing ? 1:8)) $fatal(1,"Cache launch duplicated/lost requests");
    cpu.rsp_ready=1;@(negedge clk_i);cpu.rsp_ready=0;
    cpu.req_id=37;cpu.req_size=3;cpu.req_wdata=64'hdead;cpu.req_wstrb=8'hff;
    cpu.req_rob_seq=57;checks++;
  endtask
  task automatic pulse_snoop(input logic [31:0] address);
    @(negedge clk_i);snoop_addr=address;snoop=1;
    @(negedge clk_i);snoop=0;
  endtask
  task automatic queued_write_contract;
    int before_queue;
    access_cache(32'h80007000,0,0,0);
    before_queue=requests;
    @(negedge clk_i);allow_request=0;allow_response=0;
    cpu.req_valid=1;cpu.req_write=1;cpu.req_committed=1;
    for(int i=0;i<4;i++) begin
      cpu.req_addr=32'h80007000+32'(i*8);cpu.req_id=6'(20+i);
      @(posedge clk_i);
      if(!cpu.req_ready || cpu.rsp_valid) $fatal(1,"Queued store improperly stalled or completed");
      @(negedge clk_i);
    end
    cpu.req_valid=0;cpu.req_id=37;
    // Different resident word may complete before the stores reach SRAM.
    access_cache(32'h80007020,0,0,0);
    if(requests!=before_queue) $fatal(1,"Resident read used the stalled bus");
    @(negedge clk_i);allow_request=1;
    for(int i=0;i<4;i++) begin
      wait(response_valid);@(negedge clk_i);
      if(cpu.rsp_valid || response_id!=6'(20+i) ||
         response_data!=pattern(32'h80007000+32'(i*8)))
        $fatal(1,"Out-of-order or premature queued store");
      allow_response=1;
      do @(negedge clk_i);while(!cpu.rsp_valid);
      repeat(2) begin
        if(!cpu.rsp_valid || cpu.rsp_id!=6'(20+i) || cpu.rsp_resp!=AXI_RESP_OKAY)
          $fatal(1,"Stalled queued completion lost ownership");
        @(negedge clk_i);
      end
      cpu.rsp_ready=1;@(negedge clk_i);cpu.rsp_ready=0;allow_response=0;
    end
    allow_response=1;
    if(requests-before_queue!=4) $fatal(1,"Queued store was repeated or dropped");
    checks++;
    $display("WRITE QUEUE PASS four ordered stores, independent resident load, held completions");
  endtask
  task automatic refill_race(input logic [31:0] address,input logic [31:0] written,
      input bit last_beat,input bit must_cancel);
    fork
      access_cache(address,0,0,0);
      begin
        if(last_beat) wait(dut.state_q==2'd2 && dut.beat_q==7 && mem.rsp_valid);
        else wait(mem.req_valid && mem.req_addr==address+8);
        pulse_snoop(written);
      end
    join
    before_count=requests;
    access_cache(address,0,0,0);
    if(requests-before_count!=(must_cancel?8:0))
      $fatal(1,"Snoop refill race addr=%h snoop=%h last=%b",address,written,last_beat);
  endtask
  initial begin
    cpu.req_valid=0;cpu.req_id=37;cpu.req_addr=0;cpu.req_write=0;cpu.req_size=3;
    cpu.req_wdata=64'hdead;cpu.req_wstrb=8'hff;cpu.req_priv=PRIV_M;
    cpu.req_rob_seq=57;cpu.req_committed=0;cpu.req_device=0;cpu.rsp_ready=0;
    repeat(4) @(negedge clk_i);rst_ni=1;
    read_fault=1;
    access_cache(32'h8000_0030,0,0,2);
    if(requests!=4) $fatal(1,"Failed fill must stop at the error beat");
    read_fault=0;before_count=requests;
    access_cache(32'h8000_0030,0,0,0);
    if(requests-before_count!=8) $fatal(1,"Partial/error line must not hit");
    before_count=requests;
    access_cache(32'h8000_0038,0,0,0);
    if(requests!=before_count) $fatal(1,"Successful complete line should hit");
    write_fault=1;
    access_cache(32'h8000_0030,1,0,2);
    write_fault=0;before_count=requests;
    access_cache(32'h8000_0030,0,0,0);
    if(requests-before_count!=8) $fatal(1,"Failed write must invalidate old line");
    // A device attribute forces bypass even when the address has a valid tag.
    before_count=requests;
    access_cache(32'h8000_0030,0,1,0);
    access_cache(32'h8000_0030,0,1,0);
    if(requests-before_count!=2) $fatal(1,"Device reads cannot hit or allocate");
    // An invalidate arriving during refill cancels installation of that line.
    fork
      access_cache(32'h8000_0040,0,0,0);
      begin
        wait(mem.req_valid && mem.req_addr==32'h8000_0048);
        @(negedge clk_i);invalidate=1;@(negedge clk_i);invalidate=0;
      end
    join
    // Unrelated lines and equal-index/different-tag writes must retain data.
    access_cache(32'h80000100,0,0,0);
    access_cache(32'h80000140,0,0,0);
    pulse_snoop(32'h80008100);
    before_count=requests;
    access_cache(32'h80000100,0,0,0);
    access_cache(32'h80000140,0,0,0);
    if(requests!=before_count) $fatal(1,"Snoop evicted unrelated tag/line");
    pulse_snoop(32'h80000117);
    before_count=requests;
    access_cache(32'h80000140,0,0,0);
    if(requests!=before_count) $fatal(1,"Targeted snoop flushed another line");
    access_cache(32'h80000100,0,0,0);
    if(requests!=before_count) $fatal(1,"D snoop merge unnecessarily evicted line");
    // A same-line accepted SRAM write holds a new resident read for one
    // cycle, then serves the updated bank. No miss or stale hit is permitted.
    before_count=requests;
    fork
      access_cache(32'h80000100,0,0,0);
      begin
        wait(cpu.req_valid);snoop_addr=32'h80000100;snoop=1;
        repeat(2) @(negedge clk_i);snoop=0;
      end
    join
    if(requests!=before_count) $fatal(1,"Resident snoop/read caused a refill");
    refill_race(32'h80000200,32'h80000228,0,1);
    refill_race(32'h80000240,32'h80008240,0,0);
    refill_race(32'h80000280,32'h80000240,0,0);
    refill_race(32'h800002c0,32'h800002d0,1,1);
    // Metadata of an evicted alias remains in the tag RAM but is not valid.
    // A write to that old tag on the new line's final beat must not cancel it.
    access_cache(32'h80008300,0,0,0);
    refill_race(32'h80000300,32'h80008300,1,0);
    // Once offered, a response stays stable even if its line is invalidated.
    before_count=requests;
    fork
      access_cache(32'h80000280,0,0,0);
      begin wait(cpu.rsp_valid);pulse_snoop(32'h80000280);end
    join
    if(requests!=before_count) $fatal(1,"Expected cached stalled response");
    access_cache(32'h80000280,0,0,0);
    if(requests!=before_count) $fatal(1,"D snoop merge discarded held line");
    $display("SNOOP RACES PASS bank read, refill, final beat, stalled response, unrelated alias");
    // A resident snoop byte merge and refill response may need the same bank
    // write port. The response must remain stalled, then resume without loss.
    before_count=requests;
    fork
      access_cache(32'h80000340,0,0,0);
      begin
        wait(dut.state_q==2'd2 && dut.beat_q==2 && mem.rsp_valid);
        @(negedge clk_i);snoop_addr=32'h80000100;snoop=1;
        #1;if(mem.rsp_ready) $fatal(1,"Snoop/refill bank write collision not stalled");
        repeat(3) @(negedge clk_i);snoop=0;
      end
    join
    if(requests-before_count!=8) $fatal(1,"Colliding refill beat lost/repeated");
    access_cache(32'h80000100,0,0,0);
    if(requests-before_count!=8) $fatal(1,"Resident snoop line was lost");
    $display("BANK WRITE COLLISION PASS snoop merge/refill response backpressure");
    before_count=requests;
    access_cache(32'h8000_0040,0,0,0);
    if(requests-before_count!=8) $fatal(1,"Invalidated refill became valid");
    // Hold the downstream request stalled and exercise interface assertions.
    allow_request=0;
    fork
      access_cache(32'h8000_0080,0,0,0);
      begin
        wait(mem.req_valid);
        repeat(5) @(negedge clk_i);
        allow_request=1;
      end
    join
    if(QUEUE_WRITES) queued_write_contract();
    else begin
      launch_contract(0,1,0);
      launch_contract(1,1,0);
      response_ready_contract();
    end
    launch_contract(0,0,1);
    launch_contract(1,0,1);
    launch_contract(1,0,0);
    $display("CACHE LAUNCH PASS same-edge forwarding, captured stall, bus-response completion/hold");
    // Prove actual 32 KiB capacity: every one of the 512 tags can stay live.
    @(negedge clk_i);invalidate=1;@(negedge clk_i);invalidate=0;
    before_count=requests;
    for(int line_number=0;line_number<512;line_number++)
      access_cache(32'h80000000+32'(line_number*64+(line_number%8)*8),0,0,0);
    if(requests-before_count!=4096) $fatal(1,"Cache does not contain 512 complete lines");
    before_count=requests;
    for(int line_number=0;line_number<512;line_number++)
      for(int word_number=0;word_number<8;word_number++)
        access_cache(32'h80000000+32'(line_number*64+word_number*8),0,0,0);
    if(requests!=before_count) $fatal(1,"32 KiB working set did not remain cached");
    access_cache(32'h80008000,0,0,0);
    before_count=requests;
    access_cache(32'h80000000,0,0,0);
    if(requests-before_count!=8) $fatal(1,"Direct-map alias did not evict the correct tag");
    $display("CACHE CAPACITY PASS lines=512 bytes=32768 words=4096 both-banks");
    $display("PASS rv23_cache_fault_tb checks=%0d requests=%0d",checks,requests);
    $finish;
  end
  initial begin #1000000;$fatal(1,"Cache fault watchdog");end
endmodule

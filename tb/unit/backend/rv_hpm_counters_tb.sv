`timescale 1ns/1ps
module rv_hpm_counters_tb;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,write=0,pwrite=0,pdata=0,pending,virtual_mode=0;
  logic [1:0] privilege=3,retired=0;
  logic [31:0] inhibit='1,mask,overflow;
  logic [11:0] address=0;
  logic [63:0] data=0;
  wire [31:0][63:0] counters,events;
  int checks=0;
  rv_hpm_counters dut(.clk_i(clk),.rst_ni(rst_n),.privilege_i(privilege),.virtual_i(virtual_mode),
    .retire_count_i(retired),.inhibit_i(inhibit),.write_valid_i(write),.write_address_i(address),
    .write_data_i(data),.pending_write_i(pwrite),.pending_data_i(pdata),.pending_o(pending),
    .counter_mask_o(mask),.overflow_o(overflow),.counter_o(counters),.event_o(events));
  task automatic wr(input logic[11:0] a,input logic[63:0] d);
    @(negedge clk);address=a;data=d;write=1;
    @(negedge clk);write=0;checks++;
  endtask
  task automatic clear_pending;
    @(negedge clk);pwrite=1;pdata=0;
    @(negedge clk);pwrite=0;
  endtask
  task automatic steps(input int count);
    repeat(count)@(negedge clk);
  endtask
  initial begin
    logic [63:0] before_count;
    repeat(3)@(negedge clk);rst_n=1;
    if(mask!==32'h78)$fatal(1,"implemented HPM mask");
    for(int i=0;i<32;i++)if(counters[i]!==0 || events[i]!==0)$fatal(1,"HPM reset");
    // Each actual mode can be excluded independently, including HS versus VS.
    for(int mode=0;mode<5;mode++)begin
      inhibit='1;wr(12'hb03,0);wr(12'h323,64'h4000000000000001>>mode | 1);
      for(int run_mode=0;run_mode<5;run_mode++)begin
        privilege=run_mode==0?3:(run_mode inside {1,3}?1:0);
        virtual_mode=run_mode>=3;
        before_count=counters[3];inhibit[3]=0;steps(5);inhibit[3]=1;
        if(counters[3]-before_count!==(mode==run_mode?64'd0:64'd5))
          $fatal(1,"mode filtering filter%0d actual%0d",mode,run_mode);
        checks++;
      end
    end
    privilege=3;virtual_mode=0;
    // Two retirements can wrap a counter through zero in a single cycle.
    wr(12'h323,2);wr(12'hb03,64'hfffffffffffffffe);
    retired=2;inhibit[3]=0;steps(1);inhibit[3]=1;
    if(counters[3]!==0 || !overflow[3] || !pending)$fatal(1,"HPM dual-retire overflow");
    clear_pending();
    wr(12'hb03,'1);inhibit[3]=0;steps(1);inhibit[3]=1;
    if(counters[3]!==1 || !overflow[3] || pending)$fatal(1,"OF must disable further requests");
    // Counter writes alone never create an overflow. Clear OF to rearm.
    wr(12'h323,2);wr(12'hb03,'1);
    if(overflow[3] || pending)$fatal(1,"CSR write generated overflow");
    pwrite=1;pdata=0;inhibit[3]=0;steps(1);inhibit[3]=1;pwrite=0;
    if(!pending || !overflow[3])$fatal(1,"hardware overflow must win pending clear");
    clear_pending();
    // Independent counters and selectors; unsupported selection becomes zero.
    wr(12'h324,3);wr(12'h325,4);wr(12'h326,1);
    inhibit=32'hffffff8f;retired=2;steps(7);inhibit='1;
    if(counters[4]!==7 || counters[5]!==0 || counters[6]!==7)$fatal(1,"event selectors");
    retired=0;inhibit[5]=0;steps(7);inhibit[5]=1;
    if(counters[5]!==7)$fatal(1,"no-retirement selector");
    wr(12'h326,64'hf80000000000ffff);
    if(events[6]!==64'hf800000000000000)$fatal(1,"unsupported selector WARL");
    // Absent counters/event CSRs remain zero even after writes.
    wr(12'hb07,'1);wr(12'h327,'1);
    if(counters[7]!==0 || events[7]!==0)$fatal(1,"absent HPM wrote state");
    $display("PASS rv_hpm_counters_tb checks=%0d modes/events/inhibit/overflow/rearm",checks);$finish;
  end
  initial begin #100000;$fatal(1,"HPM timeout");end
endmodule

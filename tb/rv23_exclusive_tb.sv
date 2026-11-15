`timescale 1ns/1ps
module rv23_exclusive_tb;
  import rv_soc_pkg::*;
  logic clk_i=0,rst_ni=0;
  always #5 clk_i=~clk_i;
  rv_axi4_if #(.ID_WIDTH(4)) m[3](.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(6)) s[6](.clk_i,.rst_ni);
  rv_local_mem_if local_bus(.clk_i,.rst_ni);
  logic [2:0] av,ar,al,wv,wr,br,bv,rv,rr,rl;
  logic [2:0] awv,awr,awl,wl;
  logic [2:0][3:0] id,bid,rid;
  logic [2:0][31:0] addr;
  logic [2:0][2:0] size;
  logic [2:0][63:0] wd,rd;
  logic [2:0][7:0] strb;
  logic [2:0][1:0] bp,rp;
  logic snoop;
  int writes=0,checks=0;
  always @(posedge clk_i) if(rst_ni && snoop) writes<=writes+1;
  for(genvar i=0;i<3;i++) begin:g_master
    assign m[i].aw_valid=awv[i]; assign awr[i]=m[i].aw_ready;
    assign m[i].aw_id=id[i];assign m[i].aw_addr=addr[i];
    assign m[i].aw_len=0;assign m[i].aw_size=size[i];
    assign m[i].aw_burst=1;assign m[i].aw_lock=awl[i];
    assign m[i].aw_prot=1;assign m[i].aw_cache=0;assign m[i].aw_qos=0;
    assign m[i].w_valid=wv[i];assign wr[i]=m[i].w_ready;
    assign m[i].w_data=wd[i];assign m[i].w_strb=strb[i];assign m[i].w_last=wl[i];
    assign m[i].b_ready=br[i];assign bv[i]=m[i].b_valid;
    assign bid[i]=m[i].b_id;assign bp[i]=m[i].b_resp;
    assign m[i].ar_valid=av[i];assign ar[i]=m[i].ar_ready;
    assign m[i].ar_id=id[i];assign m[i].ar_addr=addr[i];
    assign m[i].ar_len=0;assign m[i].ar_size=size[i];
    assign m[i].ar_burst=1;assign m[i].ar_lock=al[i];
    assign m[i].ar_prot=1;assign m[i].ar_cache=0;assign m[i].ar_qos=0;
    assign m[i].r_ready=rr[i];assign rv[i]=m[i].r_valid;
    assign rid[i]=m[i].r_id;assign rd[i]=m[i].r_data;
    assign rp[i]=m[i].r_resp;assign rl[i]=m[i].r_last;
  end
  rv_axi_xbar xbar(.clk_i,.rst_ni,.m0_s(m[0]),.m1_s(m[1]),.m2_s(m[2]),
    .s0_m(s[0]),.s1_m(s[1]),.s2_m(s[2]),.s3_m(s[3]),.s4_m(s[4]),.s5_m(s[5]));
  for(genvar j=1;j<6;j++) begin:g_error
    rv_axi_error_slave #(.ID_WIDTH(6)) error_slave(.clk_i,.rst_ni,.axi_s(s[j]));
  end
  rv_axi_to_local_bridge #(.AXI_ID_WIDTH(6),.ENABLE_EXCLUSIVE(1),
    .TARGET_BASE_ADDR(32'h80000000),.TARGET_SIZE_KB(1024)) bridge(
    .clk_i,.rst_ni,.axi_s(s[0]),.local_bus);
  rv23_sram sram(.clk_i,.rst_ni,.bus(local_bus),.write_snoop_o(snoop),
    .write_snoop_addr_o(),.write_snoop_data_o(),.write_snoop_strb_o());

  task automatic read_mem(input int p,input int txid,input logic[31:0] a,
    input bit exclusive,input logic[1:0] expected,input logic[63:0] value);
    @(negedge clk_i);id[p]=4'(txid);addr[p]=a;size[p]=3;al[p]=exclusive;av[p]=1;
    do @(posedge clk_i);while(!ar[p]);
    @(negedge clk_i);av[p]=0;
    wait(rv[p]);
    // Exercise held exclusive response payload and delayed consumption.
    repeat(3) @(negedge clk_i);
    if(rp[p]!==expected || rd[p]!==value || rid[p]!==4'(txid) || !rl[p])
      $fatal(1,"read p%0d addr%h resp%h data%h expected %h/%h",p,a,rp[p],rd[p],expected,value);
    rr[p]=1;@(posedge clk_i);@(negedge clk_i);rr[p]=0;checks++;
  endtask
  task automatic write_mem(input int p,input int txid,input logic[31:0] a,
    input bit exclusive,input logic[63:0] value,input logic[7:0] mask,
    input logic[1:0] expected);
    @(negedge clk_i);id[p]=4'(txid);addr[p]=a;size[p]=3;awl[p]=exclusive;awv[p]=1;
    do @(posedge clk_i);while(!awr[p]);
    @(negedge clk_i);awv[p]=0;wd[p]=value;strb[p]=mask;wl[p]=1;wv[p]=1;
    do @(posedge clk_i);while(!wr[p]);
    @(negedge clk_i);wv[p]=0;
    wait(bv[p]);repeat(3) @(negedge clk_i);
    if(bp[p]!==expected || bid[p]!==4'(txid))
      $fatal(1,"write p%0d addr%h resp%h expected%h",p,a,bp[p],expected);
    br[p]=1;@(posedge clk_i);@(negedge clk_i);br[p]=0;checks++;
  endtask
  initial begin
    av=0;al=0;awv=0;awl=0;wv=0;wl=0;br=0;rr=0;
    id=0;addr=0;size=0;wd=0;strb=0;
    repeat(4) @(negedge clk_i);rst_ni=1;
    write_mem(0,0,32'h80000000,0,64'h1122334455667788,8'hff,0);
    write_mem(0,0,32'h80000008,0,64'habcdef,8'hff,0);
    write_mem(0,0,32'h80000040,0,64'h12345678,8'hff,0);
    // SC without LR never reaches SRAM.
    write_mem(1,15,32'h80000000,1,0,8'hff,0);
    read_mem(1,15,32'h80000000,1,1,64'h1122334455667788);
    write_mem(1,15,32'h80000000,1,64'h9876,8'hff,1);
    write_mem(1,15,32'h80000000,1,0,8'hff,0);
    read_mem(0,0,32'h80000000,0,0,64'h9876);
    // Different full AXI IDs (even same local ID) retain independent monitors.
    read_mem(1,15,32'h80000000,1,1,64'h9876);
    read_mem(2,15,32'h80000040,1,1,64'h12345678);
    write_mem(1,15,32'h80000000,1,64'h9988,8'hff,1);
    write_mem(2,15,32'h80000040,1,64'h1111,8'hff,1);
    // A debug byte write in the same 64-byte granule breaks the reservation.
    read_mem(1,15,32'h80000000,1,1,64'h9988);
    write_mem(2,0,32'h80000008,0,64'h55,8'h01,0);
    write_mem(1,15,32'h80000000,1,0,8'hff,0);
    read_mem(0,0,32'h80000000,0,0,64'h9988);
    // A different granule does not spuriously break this implementation's LR.
    read_mem(1,15,32'h80000000,1,1,64'h9988);
    write_mem(2,0,32'h80000040,0,64'h2222,8'hff,0);
    write_mem(1,15,32'h80000000,1,64'h3344,8'hff,1);
    // Failed different-address SC consumes the old reservation too.
    read_mem(1,15,32'h80000000,1,1,64'h3344);
    write_mem(1,15,32'h80000008,1,0,8'hff,0);
    write_mem(1,15,32'h80000000,1,0,8'hff,0);
    read_mem(0,0,32'h80000000,0,0,64'h3344);
    if(writes!=9) $fatal(1,"failed exclusive leaked a write: count=%0d",writes);
    $display("PASS rv23_exclusive_tb checks=%0d actual_writes=%0d",checks,writes);$finish;
  end
  initial begin #200000;$fatal(1,"exclusive timeout");end
endmodule

`timescale 1ns/1ps
module rv_axi_xbar_stall_tb;
  logic clk_i=0,rst_ni=0;
  always #5 clk_i=~clk_i;
  rv_axi4_if #(.ID_WIDTH(4)) m[3] (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(6)) s[6] (.clk_i,.rst_ni);
  logic [2:0] av,wv,rv,aready,rready;
  logic [2:0][31:0] aa,ra;
  logic allow_aw=0,allow_ar=0;
  for(genvar i=0;i<3;i++) begin
    assign m[i].aw_valid=av[i];assign m[i].aw_addr=aa[i];
    assign m[i].aw_id=4'(i+5);assign m[i].aw_len=0;
    assign m[i].aw_size=3;assign m[i].aw_burst=1;
    assign m[i].aw_prot=0;assign m[i].aw_cache=0;assign m[i].aw_qos=0;
    assign m[i].w_valid=wv[i];assign m[i].w_data=64'(i+123);
    assign m[i].w_strb=8'hff;assign m[i].w_last=1;
    assign m[i].b_ready=1;
    assign m[i].ar_valid=rv[i];assign m[i].ar_addr=ra[i];
    assign m[i].ar_id=4'(i+5);assign m[i].ar_len=0;
    assign m[i].ar_size=3;assign m[i].ar_burst=1;
    assign m[i].ar_prot=0;assign m[i].ar_cache=0;assign m[i].ar_qos=0;
    assign m[i].r_ready=1;
    assign aready[i]=m[i].aw_ready;assign rready[i]=m[i].ar_ready;
  end
  for(genvar i=0;i<6;i++) begin
    assign s[i].aw_ready=i==0?allow_aw:1'b1;
    assign s[i].w_ready=1;
    assign s[i].b_valid=0;assign s[i].b_id=0;assign s[i].b_resp=0;
    assign s[i].ar_ready=i==0?allow_ar:1'b1;
    assign s[i].r_valid=0;assign s[i].r_id=0;assign s[i].r_resp=0;
    assign s[i].r_data=0;assign s[i].r_last=1;
  end
  rv_axi_xbar dut (.clk_i,.rst_ni,.m0_s(m[0]),.m1_s(m[1]),.m2_s(m[2]),
    .s0_m(s[0]),.s1_m(s[1]),.s2_m(s[2]),.s3_m(s[3]),.s4_m(s[4]),.s5_m(s[5]));
  task automatic reset_case;
    @(negedge clk_i);rst_ni=0;av=0;wv=0;rv=0;allow_aw=0;allow_ar=0;
    repeat(3) @(negedge clk_i);rst_ni=1;
  endtask
  initial begin
    av=0;wv=0;rv=0;
    for(int i=0;i<3;i++) begin aa[i]=32'h80000000+32'(i*8);ra[i]=aa[i];end
    reset_case();
    @(negedge clk_i);rv[1]=1;
    repeat(2) @(negedge clk_i);
    rv[0]=1;
    #1;
    if(s[0].ar_addr!==32'h80000008 || s[0].ar_id!==6'h16)
      $fatal(1,"AR ownership changed under backpressure");
    repeat(5) begin
      @(negedge clk_i);
      if(!s[0].ar_valid || s[0].ar_addr!==32'h80000008 || s[0].ar_id!==6'h16)
        $fatal(1,"AR ownership changed under backpressure");
    end
    allow_ar=1;
    @(posedge clk_i);if(!rready[1] || rready[0]) $fatal(1,"AR wrong owner accepted");
    @(negedge clk_i);rv[1]=0;
    @(posedge clk_i);if(!rready[0]) $fatal(1,"AR next requester not accepted");
    @(negedge clk_i);rv[0]=0;
    reset_case();
    @(negedge clk_i);av[1]=1;
    repeat(2) @(negedge clk_i);
    av[0]=1;
    #1;
    if(s[0].aw_addr!==32'h80000008 || s[0].aw_id!==6'h16)
      $fatal(1,"AW ownership changed under backpressure");
    repeat(5) begin
      @(negedge clk_i);
      if(!s[0].aw_valid || s[0].aw_addr!==32'h80000008 || s[0].aw_id!==6'h16)
        $fatal(1,"AW ownership changed under backpressure");
    end
    allow_aw=1;
    @(posedge clk_i);if(!aready[1] || aready[0]) $fatal(1,"AW wrong owner accepted");
    @(negedge clk_i);av[1]=0;wv[1]=1;
    @(posedge clk_i);
    @(negedge clk_i);wv[1]=0;
    @(posedge clk_i);if(!aready[0]) $fatal(1,"AW next requester not accepted");
    @(negedge clk_i);av[0]=0;
    $display("PASS rv_axi_xbar_stall_tb AR/AW winner hold, ID prefix, handshake ownership");
    $finish;
  end
  initial begin #10000;$fatal(1,"Crossbar stall watchdog");end
endmodule

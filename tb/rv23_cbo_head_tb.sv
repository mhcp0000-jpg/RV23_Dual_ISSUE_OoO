`timescale 1ns/1ps
module rv23_cbo_head_tb;
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
  for(genvar i=0;i<3;i++) if(i!=1) begin:g_master
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
  logic request_valid=0,request_ready,response_valid,response_ready=0,exception_flag;
  logic [63:0] address=0,tval,menvcfg=0,senvcfg=0;
  logic [11:0] operation=0;
  logic [31:0] instruction;
  logic [5:0] cause;
  rv_ooo_pkg::privilege_e privilege=rv_ooo_pkg::PRIV_M;
  logic [7:0][7:0] cfg=0;
  logic [7:0][61:0] pmpaddr='1;
  logic inv_valid,inv_ready=0;
  int invalidations=0;
  assign instruction={operation,5'd8,3'd2,5'd0,7'h0f};
  always @(posedge clk_i) if(rst_ni && inv_valid && inv_ready) invalidations<=invalidations+1;
  always @(negedge clk_i) inv_ready<=inv_valid;
  rv_local_mem_if cbo_bus(.clk_i,.rst_ni);
  assign cbo_bus.req_id=6'he;assign cbo_bus.req_write=1;assign cbo_bus.req_size=3;
  assign cbo_bus.req_wdata=0;assign cbo_bus.req_wstrb=8'hff;
  assign cbo_bus.req_priv=rv_soc_pkg::PRIV_M;assign cbo_bus.req_rob_seq=0;
  assign cbo_bus.req_committed=1;assign cbo_bus.req_device=0;
  rv_local_to_axi_bridge cbo_bridge(.clk_i,.rst_ni,.local_bus(cbo_bus),.axi_m(m[1]));
  rv23_cbo_head #(.HAS_MMU(0)) dut(.clk_i,.rst_ni,.invalidate_i(1'b0),
    .request_valid_i(request_valid),.request_ready_o(request_ready),.address_i(address),
    .operation_i(operation),.instruction_i(instruction),.privilege_i(privilege),
    .effective_privilege_i(privilege),.mstatus_i(64'b0),.satp_i(64'b0),
    .menvcfg_i(menvcfg),.senvcfg_i(senvcfg),.pmpcfg_i(cfg),.pmpaddr_i(pmpaddr),
    .response_valid_o(response_valid),.response_ready_i(response_ready),
    .response_exception_o(exception_flag),.response_cause_o(cause),.response_tval_o(tval),
    .cache_invalidate_valid_o(inv_valid),.cache_invalidate_ready_i(inv_ready),
    .ptw_valid_o(),.ptw_device_o(),.ptw_ready_i(1'b0),.ptw_address_o(),
    .ptw_response_valid_i(1'b0),.ptw_response_ready_o(),.ptw_data_i(64'b0),.ptw_error_i(1'b0),
    .write_valid_o(cbo_bus.req_valid),.write_ready_i(cbo_bus.req_ready),
    .write_address_o(cbo_bus.req_addr),.write_response_valid_i(cbo_bus.rsp_valid),
    .write_response_ready_o(cbo_bus.rsp_ready),
    .write_response_error_i(cbo_bus.rsp_resp[1] || cbo_bus.rsp_replay!=MEM_REPLAY_NONE));
  task automatic cbo(input int op,input logic[63:0] a,input int expected_cause=0,
    input logic[63:0] expected_tval=0);
    @(negedge clk_i);operation=12'(op);address=a;request_valid=1;
    do @(posedge clk_i);while(!request_ready);
    @(negedge clk_i);request_valid=0;wait(response_valid);
    repeat(3) @(negedge clk_i);
    if(exception_flag!==(expected_cause!=0) ||
       (expected_cause!=0 && (cause!=6'(expected_cause) || tval!==expected_tval)))
      $fatal(1,"CBO op%0d addr%h exception%0d cause%0d tval%h expected%0d/%h",
        op,a,exception_flag,cause,tval,expected_cause,expected_tval);
    response_ready=1;@(posedge clk_i);@(negedge clk_i);response_ready=0;checks++;
  endtask
  initial begin
    int before_writes;
    av=0;al=0;awv=0;awl=0;wv=0;wl=0;br=0;rr=0;
    id=0;addr=0;size=0;wd=0;strb=0;
    repeat(4) @(negedge clk_i);rst_ni=1;
    for(int n=0;n<10;n++)write_mem(2,0,32'h800700f8+32'(n*8),0,64'h12340000+64'(n),8'hff,0);
    before_writes=writes;
    cbo(4,64'h8007013f);
    if(writes-before_writes!=8)$fatal(1,"CBO.ZERO did not complete exactly eight bus writes");
    for(int n=0;n<8;n++)read_mem(2,0,32'h80070100+32'(n*8),0,0,0);
    read_mem(2,0,32'h800700f8,0,0,64'h12340000);
    read_mem(2,0,32'h80070140,0,0,64'h12340009);
    cbo(1,64'h8007013f);if(invalidations!=0)$fatal(1,"clean invalidated unnecessarily");
    cbo(0,64'h8007013f);cbo(2,64'h8007013f);
    if(invalidations!=2)$fatal(1,"invalidate/flush missing");
    // Main-memory ZERO is supported; MMIO ZERO cannot write peripherals.
    cbo(4,64'h02000001,7,64'h02000001);
    cbo(1,64'h02000001); // Uncached management does not read an MMIO register.
    cbo(1,64'h90000000,7,64'h90000000);
    // CSR controls are checked in architectural privilege before MPRV access.
    privilege=rv_ooo_pkg::PRIV_S;cfg[0]=8'h0f;
    cbo(0,64'h80070100,2,64'h0004200f);
    cbo(1,64'h80070100,2,64'h0014200f);
    cbo(4,64'h80070100,2,64'h0044200f);
    menvcfg=64'hf0;
    cbo(1,64'h80070100);
    privilege=rv_ooo_pkg::PRIV_U;
    cbo(2,64'h80070100,2,64'h0024200f);
    senvcfg=64'h2000000f0;
    cbo(4,64'hfe00000080070101);
    // Read-only PMP permits management but forbids ZERO before any writes.
    cfg[0]=8'h09;before_writes=writes;
    cbo(1,64'h80070101);
    cbo(4,64'h80070101,7,64'h80070101);
    if(writes!=before_writes)$fatal(1,"denied ZERO wrote memory");
    $display("PASS rv23_cbo_head_tb checks=%0d invalidate=%0d ZERO/CSR/PMP/MMIO/pointer",checks,invalidations);$finish;
  end
  initial begin #2000000;$fatal(1,"CBO timeout");end
endmodule

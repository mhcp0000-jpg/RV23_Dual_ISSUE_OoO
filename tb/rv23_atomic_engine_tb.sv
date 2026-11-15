`timescale 1ns/1ps
module rv23_atomic_engine_tb;
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
  logic atom_valid=0,atom_ready,atom_rsp,atom_rsp_ready=0,atom_exception;
  logic [31:0] atom_address=0;
  logic [63:0] atom_operand=0,atom_result;
  logic [4:0] atom_operation=0;
  logic atom_word=0,clear_lr=0,lr_valid,atom_idle;
  logic [5:0] atom_cause;
  int atomic_reads=0;
  always @(posedge clk_i) if(rst_ni && m[1].ar_valid && m[1].ar_ready)
    atomic_reads<=atomic_reads+1;
  rv23_atomic_engine engine(.clk_i,.rst_ni,
    .request_valid_i(atom_valid),.request_ready_o(atom_ready),
    .request_address_i(atom_address),.request_operand_i(atom_operand),
    .request_operation_i(atom_operation),.request_word_i(atom_word),
    .request_privileged_i(1'b1),.clear_reservation_i(clear_lr),
    .write_snoop_i(snoop),.write_snoop_address_i(local_bus.req_addr),
    .reservation_valid_o(lr_valid),.idle_o(atom_idle),
    .response_valid_o(atom_rsp),.response_ready_i(atom_rsp_ready),
    .response_data_o(atom_result),.response_exception_o(atom_exception),
    .response_cause_o(atom_cause),.axi_m(m[1]));
  task automatic atomic(input logic[4:0] op,input bit w,input logic[31:0] a,
    input logic[63:0] operand,input logic[63:0] expected,input int cause=0);
    @(negedge clk_i);atom_operation=op;atom_word=w;atom_address=a;
    atom_operand=operand;atom_valid=1;
    do @(posedge clk_i);while(!atom_ready);
    @(negedge clk_i);atom_valid=0;wait(atom_rsp);
    repeat(3) @(negedge clk_i);
    if(atom_exception!==(cause!=0) || (cause!=0 && atom_cause!=6'(cause)) ||
       (cause==0 && atom_result!==expected))
      $fatal(1,"atomic op%h word%0d addr%h result%h expected%h cause%0d expected%0d",
        op,w,a,atom_result,expected,atom_cause,cause);
    atom_rsp_ready=1;@(posedge clk_i);@(negedge clk_i);atom_rsp_ready=0;checks++;
  endtask
  logic[4:0] ops[9]='{0,1,4,8,12,16,20,24,28};
  function automatic logic[63:0] oracle(input logic[63:0] a,b,input int op,input bit w);
    logic [31:0] x,y,z;
    logic [63:0] r;
    x=a[31:0];y=b[31:0];z=0;r=0;
    if(w) begin
      case(op)
        0:z=x+y;1:z=y;4:z=x^y;8:z=x|y;12:z=x&y;
        16:z=$signed(x)<$signed(y)?x:y;20:z=$signed(x)>$signed(y)?x:y;
        24:z=x<y?x:y;28:z=x>y?x:y;
      endcase
      return {32'b0,z};
    end
    case(op)
      0:r=a+b;1:r=b;4:r=a^b;8:r=a|b;12:r=a&b;
      16:r=$signed(a)<$signed(b)?a:b;20:r=$signed(a)>$signed(b)?a:b;
      24:r=a<b?a:b;28:r=a>b?a:b;
    endcase
    return r;
  endfunction
  initial begin
    logic[63:0] a,b,old,expected,container;
    logic[31:0] address;
    int before_reads;
    av=0;al=0;awv=0;awl=0;wv=0;wl=0;br=0;rr=0;
    id=0;addr=0;size=0;wd=0;strb=0;
    repeat(4) @(negedge clk_i);rst_ni=1;
    write_mem(0,0,32'h80000000,0,64'h88776655fedcba98,8'hff,0);
    atomic(3,0,32'h80000000,0,1);
    atomic(2,0,32'h80000000,0,64'h88776655fedcba98);
    if(!lr_valid)$fatal(1,"LR did not reserve");
    atomic(3,0,32'h80000000,64'h12345678,0);
    atomic(3,0,32'h80000000,0,1);
    read_mem(0,0,32'h80000000,0,0,64'h12345678);
    atomic(2,0,32'h80000000,0,64'h12345678);
    write_mem(2,0,32'h80000000,0,64'hff,8'h01,0);
    if(lr_valid)$fatal(1,"debug snoop did not invalidate LR");
    atomic(3,0,32'h80000000,0,1);
    atomic(2,0,32'h80000000,0,64'h123456ff);
    @(negedge clk_i);clear_lr=1;@(negedge clk_i);clear_lr=0;
    atomic(3,0,32'h80000000,0,1);
    // W lane selection, sign extension and unchanged neighboring word.
    write_mem(0,0,32'h80000000,0,64'h8000000101234567,8'hff,0);
    atomic(2,1,32'h80000004,0,64'hffffffff80000001);
    atomic(3,1,32'h80000004,64'habcdef0187654321,0);
    read_mem(0,0,32'h80000000,0,0,64'h8765432101234567);
    // Independent integer oracle covers every W/D AMO and both word lanes.
    for(int w=0;w<2;w++) for(int lane=0;lane<(w?2:1);lane++)
      for(int op=0;op<9;op++) for(int v=0;v<8;v++) begin
        a=(64'h80000000ffffffff >> v) ^ (64'h0102030405060708 * 64'(v));
        b=(64'hfedcba9876543210 << v) ^ (64'h1111111111111111 * 64'(v));
        container=w?((64'ha5a5a5a5a5a5a5a5 & ~(64'hffffffff << (lane*32))) |
                     ((a & 64'hffffffff) << (lane*32))):a;
        address=32'h80000000+32'(lane*4);
        old=w?{{32{a[31]}},a[31:0]}:a;
        expected=oracle(a,b,int'(ops[op]),w!=0);
        if(w)expected=(container & ~(64'hffffffff << (lane*32))) |
                       (expected << (lane*32));
        write_mem(0,0,32'h80000000,0,container,8'hff,0);
        atomic(ops[op],w!=0,address,b,old);
        read_mem(0,0,32'h80000000,0,0,expected);
      end
    // Force a debug write between the exclusive read and exclusive write.
    write_mem(0,0,32'h80000000,0,10,8'hff,0);
    before_reads=atomic_reads;
    fork
      atomic(0,0,32'h80000000,7,100);
      begin
        wait(m[1].ar_valid && m[1].ar_ready);@(posedge clk_i);
        write_mem(2,0,32'h80000000,0,100,8'hff,0);
      end
    join
    if(atomic_reads-before_reads<2)$fatal(1,"AMO collision did not retry");
    read_mem(0,0,32'h80000000,0,0,107);
    // Faults have no bus side effects, including SC with an invalid address.
    atomic(2,0,32'h80000002,0,0,4);
    atomic(3,0,32'h80000002,0,0,6);
    atomic(0,0,32'h02000000,0,0,7);
    atomic(2,0,32'h02000000,0,0,5);
    atomic(31,0,32'h80000000,0,0,2);
    $display("PASS rv23_atomic_engine_tb checks=%0d atomic_reads=%0d",checks,atomic_reads);$finish;
  end
  initial begin #2000000;$fatal(1,"atomic engine timeout");end
endmodule

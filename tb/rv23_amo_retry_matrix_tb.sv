`timescale 1ns/1ps
module rv23_amo_retry_matrix_tb;
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
  logic [63:0] captured_read,captured_result;
  int failed_exclusives=0;
  always @(posedge clk_i) if(rst_ni && m[1].b_valid && m[1].b_ready && m[1].b_resp==0) failed_exclusives<=failed_exclusives+1;
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
    captured_read=rd[p];
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
  // Test-only AW backpressure keeps the exclusive interval open for the other master.
  rv_axi4_if #(.ID_WIDTH(4)) e_axi(.clk_i,.rst_ni);
  logic hold_atomic_aw=0;
  assign m[1].aw_id=e_axi.aw_id;
  assign m[1].aw_addr=e_axi.aw_addr;
  assign m[1].aw_len=e_axi.aw_len;
  assign m[1].aw_size=e_axi.aw_size;
  assign m[1].aw_burst=e_axi.aw_burst;
  assign m[1].aw_lock=e_axi.aw_lock;
  assign m[1].aw_prot=e_axi.aw_prot;
  assign m[1].aw_cache=e_axi.aw_cache;
  assign m[1].aw_qos=e_axi.aw_qos;
  assign m[1].w_data=e_axi.w_data;
  assign m[1].w_strb=e_axi.w_strb;
  assign m[1].w_last=e_axi.w_last;
  assign m[1].w_valid=e_axi.w_valid;
  assign m[1].ar_id=e_axi.ar_id;
  assign m[1].ar_addr=e_axi.ar_addr;
  assign m[1].ar_len=e_axi.ar_len;
  assign m[1].ar_size=e_axi.ar_size;
  assign m[1].ar_burst=e_axi.ar_burst;
  assign m[1].ar_lock=e_axi.ar_lock;
  assign m[1].ar_prot=e_axi.ar_prot;
  assign m[1].ar_cache=e_axi.ar_cache;
  assign m[1].ar_qos=e_axi.ar_qos;
  assign m[1].ar_valid=e_axi.ar_valid;
  assign m[1].b_ready=e_axi.b_ready;
  assign m[1].r_ready=e_axi.r_ready;
  assign m[1].aw_valid=e_axi.aw_valid && !hold_atomic_aw;
  assign e_axi.aw_ready=m[1].aw_ready && !hold_atomic_aw;
  assign e_axi.w_ready=m[1].w_ready;
  assign e_axi.ar_ready=m[1].ar_ready;
  assign e_axi.b_id=m[1].b_id;
  assign e_axi.b_resp=m[1].b_resp;
  assign e_axi.b_valid=m[1].b_valid;
  assign e_axi.r_id=m[1].r_id;
  assign e_axi.r_data=m[1].r_data;
  assign e_axi.r_resp=m[1].r_resp;
  assign e_axi.r_last=m[1].r_last;
  assign e_axi.r_valid=m[1].r_valid;
  rv23_atomic_engine engine(.clk_i,.rst_ni,
    .request_valid_i(atom_valid),.request_ready_o(atom_ready),
    .request_address_i(atom_address),.request_operand_i(atom_operand),
    .request_operation_i(atom_operation),.request_word_i(atom_word),
    .request_privileged_i(1'b1),.clear_reservation_i(clear_lr),
    .write_snoop_i(snoop),.write_snoop_address_i(local_bus.req_addr),
    .reservation_valid_o(lr_valid),.idle_o(atom_idle),
    .response_valid_o(atom_rsp),.response_ready_i(atom_rsp_ready),
    .response_data_o(atom_result),.response_exception_o(atom_exception),
    .response_cause_o(atom_cause),.axi_m(e_axi));
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
    captured_result=atom_result;
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
    logic[63:0] initial_value,operand,intervening,target_value,expected,old_value,observed_target;
    logic[31:0] address,debug_address;
    logic[7:0] debug_mask;
    int before_reads,before_failed,before_writes,cases_count;
    av=0;al=0;awv=0;awl=0;wv=0;wl=0;br=0;rr=0;
    id=0;addr=0;size=0;wd=0;strb=0;cases_count=0;
    repeat(4)@(negedge clk_i);rst_ni=1;
    for(int shape=0;shape<3;shape++)for(int op=0;op<9;op++)
      for(int kind=0;kind<5;kind++)for(int rounds=1;rounds<=2;rounds++)begin
        bit word_value;
        int shift;
        word_value=shape!=0;shift=shape==2?32:0;
        address=32'h80000000+32'(shape==2?4:0);
        initial_value=64'h8123456789abcdef;
        operand=64'hfedcba9876543210;
        target_value=initial_value;
        debug_address=kind==2?32'h80000008:kind==3?32'h80000040:32'h80000000;
        debug_mask=kind==1?(8'h01<<(word_value?(shift/8):2)):8'hff;
        for(int round=1;round<=rounds;round++)begin
          intervening=64'h90abcdef87654321 ^ (64'h0101010101010101*64'(round));
          if(kind<2)for(int byte_id=0;byte_id<8;byte_id++)
            if(debug_mask[byte_id])target_value[byte_id*8+:8]=intervening[byte_id*8+:8];
        end
        old_value=word_value?{{32{target_value[shift+31]}},target_value[shift+:32]}:target_value;
        expected=oracle(target_value>>shift,operand,int'(ops[op]),word_value);
        if(word_value)expected=(target_value & ~(64'hffffffff<<shift)) | (expected<<shift);
        write_mem(0,0,32'h80000000,0,initial_value,8'hff,0);
        write_mem(0,0,32'h80000008,0,64'h1122334455667788,8'hff,0);
        write_mem(0,0,32'h80000040,0,64'h1122334455667788,8'hff,0);
        before_reads=atomic_reads;before_failed=failed_exclusives;before_writes=writes;
        hold_atomic_aw=1;
        fork
          atomic(ops[op],word_value,address,operand,old_value);
          begin
            for(int round=1;round<=(kind<3?rounds:1);round++)begin
              wait(atomic_reads>=before_reads+round);
              hold_atomic_aw=1;
              if(kind==4)repeat(rounds)read_mem(2,3,debug_address,0,0,initial_value);
              else begin
                intervening=64'h90abcdef87654321 ^ (64'h0101010101010101*64'(round));
                write_mem(2,3,debug_address,0,intervening,debug_mask,0);
                // A second unrelated write uses no new exclusive-read trigger.
                if(kind==3 && rounds==2)begin
                  intervening=64'h90abcdef87654321 ^ 64'h0202020202020202;
                  write_mem(2,3,debug_address,0,intervening,debug_mask,0);
                end
              end
              @(negedge clk_i);hold_atomic_aw=0;
            end
          end
        join
        if(atomic_reads-before_reads!=(kind<3?rounds+1:1) ||
           failed_exclusives-before_failed!=(kind<3?rounds:0) ||
           writes-before_writes!=1+(kind==4?0:rounds))
          $fatal(1,"Retry/write leakage kind=%0d rounds=%0d reads=%0d failed=%0d writes=%0d",
            kind,rounds,atomic_reads-before_reads,failed_exclusives-before_failed,writes-before_writes);
        read_mem(0,0,32'h80000000,0,0,expected);
        observed_target=captured_read;
        if(kind==2 || kind==3)read_mem(0,0,debug_address,0,0,intervening);
        $display("AMO_RETRY shape=%0d op=%0d kind=%0d rounds=%0d reads=%0d failed=%0d writes=%0d old=%016h memory=%016h",
          shape,ops[op],kind,rounds,atomic_reads-before_reads,failed_exclusives-before_failed,
          writes-before_writes,captured_result,observed_target);
        cases_count++;
      end
    if(cases_count!=270)$fatal(1,"Missing matrix case");
    $display("PASS rv23_amo_retry_matrix_tb cases=%0d",cases_count);$finish;
  end
  initial begin #20000000;$fatal(1,"AMO retry matrix timeout");end
endmodule

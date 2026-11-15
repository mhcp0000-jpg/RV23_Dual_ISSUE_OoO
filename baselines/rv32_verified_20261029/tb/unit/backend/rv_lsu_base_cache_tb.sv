// Actual core-sized cache regression; wrapper geometry is unit-only.
module rv_lsu_base_cache_tb #(
  parameter int XLEN=32,
  parameter int ENTRIES=56,
  parameter int WBP=12
);
  import rv_ooo_pkg::*;
  localparam logic [XLEN-1:0] A=XLEN'(64'hfedcba9876543210);
  localparam logic [XLEN-1:0] B=XLEN'(64'h123456789abcdef0);
  localparam logic [XLEN-1:0] C=XLEN'(64'h810000004321abcd);
  localparam logic [XLEN-1:0] D=XLEN'(64'h7e0000007654dcba);
  logic clk=0,rst=0;
  always #5 clk=~clk;
  logic [1:0] dv,accept,cv;
  logic dready,flush_all,flush_younger,empty,full;
  logic [7:0] boundary;
  logic [1:0][7:0] seq,cseq;
  fu_class_e [1:0] fu,cfu;
  logic [1:0][2:0] used,ready;
  reg_class_e [1:0][2:0] cls;
  logic [1:0][2:0][6:0] tags;
  logic [1:0][XLEN-1:0] base,cbase;
  logic [WBP-1:0] wv;
  reg_class_e [WBP-1:0] wc;
  logic [WBP-1:0][6:0] wt;
  logic [WBP-1:0][XLEN-1:0] wd;
  logic [1:0] addr_phase,data_phase;
  logic [$clog2(ENTRIES+1)-1:0] count;
  int checks=0,cases=0;
  bit negative;
  rv_issue_queue #(.XLEN(XLEN),.ENTRIES(ENTRIES),.ROB_SEQ_WIDTH(8),
    .WRITEBACK_PORTS(WBP)) u_dut(
    .clk_i(clk),.rst_ni(rst),.dispatch_valid_i(dv),.dispatch_ready_o(dready),
    .dispatch_sequence_i(seq),.dispatch_fu_i(fu),
    .dispatch_port_mask_i({5'b01100,5'b01100}),
    .dispatch_src_used_i(used),.dispatch_src_class_i(cls),
    .dispatch_src_phys_i(tags),.dispatch_src_ready_i(ready),.dispatch_lsu_base_i(base),
    .dispatch_destination_valid_i('0),.dispatch_destination_class_i('0),
    .dispatch_destination_phys_i('0),.dispatch_pc_i('0),.dispatch_instruction_i('0),
    .dispatch_inst_len_i('0),.dispatch_prediction_i('0),.dispatch_immediate_i('0),
    .dispatch_operation_i('0),.dispatch_use_pc_i('0),.dispatch_use_immediate_i('0),
    .dispatch_word_operation_i('0),.dispatch_mem_size_i('0),.dispatch_mem_unsigned_i('0),
    .dispatch_rounding_mode_i('0),.dispatch_checkpoint_valid_i('0),
    .dispatch_checkpoint_id_i('0),.dispatch_lq_index_i('0),.dispatch_sq_index_i('0),
    .writeback_valid_i(wv),.writeback_class_i(wc),.writeback_phys_i(wt),.writeback_data_i(wd),
    .candidate_valid_o(cv),.candidate_accept_i(accept),.candidate_sequence_o(cseq),
    .candidate_fu_o(cfu),.candidate_lsu_base_o(cbase),
    .candidate_store_address_valid_o(addr_phase),.candidate_store_data_valid_o(data_phase),
    .flush_all_i(flush_all),.flush_younger_i(flush_younger),.flush_sequence_i(boundary),
    .empty_o(empty),.full_o(full),.count_o(count));
  task automatic idle;
    dv='0;accept='0;wv='0;wc='0;wt='0;wd='0;
    fu='0;seq='0;used='0;ready='0;cls='0;tags='0;base='0;
    flush_all=0;flush_younger=0;boundary=0;
  endtask
  task automatic cycle;
    @(negedge clk);idle();
  endtask
  task automatic tick;
    @(posedge clk);#1;
  endtask
  task automatic check_candidate(input int slot,input logic[7:0] age,input logic[XLEN-1:0] value);
    checks++;
    if(cv[slot]!==1'b1 || cseq[slot]!==age)
      $fatal(1,"LSU_BASE_CACHE candidate mismatch slot=%0d seq=%0d",slot,age);
    if(cbase[slot]!==value)
      $fatal(1,"LSU_BASE_CACHE value mismatch slot=%0d got=%h expected=%h",slot,cbase[slot],value);
  endtask
  task automatic check_reset;
    checks++;
    if(!empty || count!='0) $fatal(1,"LSU_BASE_CACHE reset occupancy");
    for(int e=0;e<ENTRIES;e++)
      if(u_dut.lsu_base_q[e]!=='0) $fatal(1,"LSU_BASE_CACHE unreset FF e=%0d",e);
  endtask
  task automatic fresh;
    cycle();flush_all=1;tick();check_reset();cycle();
  endtask
  task automatic load(input int lane,input logic[7:0] age,input logic[6:0] tag,
                       input logic[XLEN-1:0] value,input bit is_ready);
    dv[lane]=1;seq[lane]=age;fu[lane]=FU_LOAD;used[lane]=3'b001;
    cls[lane][0]=REG_INT;tags[lane][0]=tag;ready[lane]=3'b110;
    ready[lane][0]=is_ready;base[lane]=value;
  endtask
  task automatic wake(input int port,input logic[6:0] tag,input logic[XLEN-1:0] value);
    wv[port]=1;wc[port]=REG_INT;wt[port]=tag;wd[port]=value;
  endtask
  initial begin
    negative=$test$plusargs("cache_checker_negative");idle();
    repeat(2)tick();cycle();rst=1;#1;check_reset();

    // Ready-at-dispatch and held issue: changing inactive dispatch data must
    // not corrupt a resident cached value.
    load(0,10,5,A,1);tick();cycle();#1;
    check_candidate(0,10,negative ? (A ^ XLEN'(1)) : A);
    repeat(3) begin base='1;tick();cycle();#1;check_candidate(0,10,A);end
    cases++;

    // Same-cycle wake/issue observes the broadcast before the cache FF edge.
    fresh();load(0,11,7,'0,0);tick();cycle();#1;
    if(cv!='0) $fatal(1,"LSU_BASE_CACHE not-ready load issued");
    wake(0,7,B);#1;check_candidate(0,11,B);tick();cycle();#1;
    check_candidate(0,11,B);accept=1;tick();cycle();#1;
    if(!empty) $fatal(1,"LSU_BASE_CACHE load did not retire from IQ");
    cases++;

    // Split store: address is issued before FP data. A later FP wake cannot
    // change its integer base, and the second store phase reuses that base.
    fresh();load(0,12,6,A,1);fu[0]=FU_STORE;used[0]=3'b011;
    cls[0][1]=REG_FP;tags[0][1]=9;ready[0][1]=0;
    tick();cycle();#1;check_candidate(0,12,A);
    if(!addr_phase[0] || data_phase[0]) $fatal(1,"LSU_BASE_CACHE store address phase");
    accept=1;tick();cycle();#1;
    if(cv!='0 || count!=1) $fatal(1,"LSU_BASE_CACHE store failed data wait");
    wv[0]=1;wc[0]=REG_FP;wt[0]=9;wd[0]=D;#1;check_candidate(0,12,A);
    if(addr_phase[0] || !data_phase[0]) $fatal(1,"LSU_BASE_CACHE store data phase");
    accept=1;tick();cycle();#1;
    if(!empty) $fatal(1,"LSU_BASE_CACHE store retained after data phase");
    cases++;

    // Younger-only flush, including sequence wrap. Older wakeup survives;
    // the killed younger value cannot become an issue candidate.
    fresh();load(0,250,10,'0,0);load(1,3,11,'0,0);tick();cycle();
    flush_younger=1;boundary=250;wake(0,10,B);wake(1,11,C);tick();cycle();#1;
    check_candidate(0,250,B);
    if(cv[1] || count!=1) $fatal(1,"LSU_BASE_CACHE younger flush failed");
    cases++;

    // Full flush dominates simultaneous dispatch and broadcast, and resets
    // every cache FF; a later generation gets its new value.
    cycle();flush_all=1;load(0,20,12,C,1);wake(0,10,D);tick();check_reset();
    cycle();load(0,21,12,D,1);tick();cycle();#1;check_candidate(0,21,D);
    cases++;

    // Dual dispatch with two matching wakeups: broadcast values override
    // stale dispatch data on the SAME allocation edge.
    fresh();load(0,30,12,'0,0);load(1,31,13,'0,0);
    wake(0,12,C);wake(1,13,D);tick();cycle();#1;
    check_candidate(0,30,C);check_candidate(1,31,D);
    accept=3;tick();cycle();#1;
    if(!empty) $fatal(1,"LSU_BASE_CACHE dual acceptance failed");
    cases++;

    // Reset while an entry is pending must clear both validity and all data.
    load(0,40,5,A,1);tick();cycle();#1;check_candidate(0,40,A);
    rst=0;tick();check_reset();cycle();rst=1;#1;check_reset();cases++;
    if(cases!=7 || checks<15) $fatal(1,"LSU_BASE_CACHE insufficient coverage");
    $display("PASS rv_lsu_base_cache_tb XLEN=%0d ENTRIES=%0d WBP=%0d cases=%0d checks=%0d",XLEN,ENTRIES,WBP,cases,checks);
    $finish;
  end
  initial begin #10000;$fatal(1,"LSU_BASE_CACHE timeout");end
endmodule


module rv_lsu_base_cache64_tb;
  rv_lsu_base_cache_tb #(.XLEN(64),.ENTRIES(56),.WBP(12)) u_test();
endmodule

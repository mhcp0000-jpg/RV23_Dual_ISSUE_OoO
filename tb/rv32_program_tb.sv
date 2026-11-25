`timescale 1ns/1ps
// One reusable native model for legacy HostIF and HTIF ELF regressions.
module rv32_program_tb #(
  parameter int unsigned XLEN=32,
  parameter bit HAS_A=0,
  parameter bit HAS_CBO=0,
  parameter bit HAS_MISALIGNED=0,
  parameter bit HAS_V=0,
  parameter bit HAS_H=0,
  parameter bit HAS_D=0,HAS_ZFHMIN=0,HAS_ZFA=0,
  parameter bit HAS_SSNPM=0,
  parameter bit HAS_ZAWRS=0,HAS_ZIMOP=0,HAS_ZCMOP=0,HAS_ZCB=0,HAS_SVINVAL=0,
  parameter bit HAS_B=0,
  parameter bit HAS_SMODE=0,
  parameter bit HAS_MMU=0,
  parameter bit HAS_ZICOND=0
);
  import rv_soc_pkg::*;
  logic clk=0,rst_n=0;
  always #5 clk=~clk;
  rv_axi4_if #(.ID_WIDTH(4)) host_axi (.clk_i(clk),.rst_ni(rst_n));
  logic soc_ready,load_done,load_failed,boot_wait=0;
  logic [31:0] entry,flags,event_data;
  logic event_valid,event_ready;
  host_event_e event_kind;
  logic htif_exit;
  logic [31:0] htif_code;
  logic halt=0,halted;
  logic [31:1] external_irq;
  logic [1:0] trace_valid,trace_we,trace_fp,trace_trap;
  logic [1:0][XLEN-1:0] trace_pc,trace_data,trace_tval;
  logic [1:0][31:0] trace_instr;
  logic [1:0][4:0] trace_rd;
  logic [1:0][5:0] trace_cause;
  integer commits=0,timeout_cycles=2000000,expected_exit_code=0;
  bit finished=0;
  // Count only after AXI ELF loading, using the same observation in both runs.
  longint unsigned perf_i_hit=0,perf_i_miss=0,perf_d_hit=0,perf_d_miss=0;
  longint unsigned perf_i_engine=0,perf_d_write=0,perf_d_fill=0,perf_dual_d=0,perf_if_wait=0;
  longint unsigned perf_snoops=0,perf_i_discard=0,perf_d_discard=0;
  always @(posedge clk) if(rst_n && load_done) begin
    perf_i_hit+=$countones(u_dut.u_icache.hit_accept);
    perf_i_miss+=$countones(u_dut.u_icache.miss_accept);
    perf_d_hit+=$countones(u_dut.u_dcache.hit_accept);
    perf_d_miss+=$countones(u_dut.u_dcache.miss_accept);
    if(u_dut.u_icache.state_q!=2'd0) perf_i_engine++;
    if(u_dut.u_dcache.state_q!=2'd0) begin
      if(u_dut.u_dcache.write_q) perf_d_write++;
      else perf_d_fill++;
    end
    if(&u_dut.u_dcache.hit_accept) perf_dual_d++;
    if(u_dut.imem_req_valid && !u_dut.imem_req_ready) perf_if_wait++;
    if(u_dut.sram_write_snoop) perf_snoops++;
    if(u_dut.u_icache.invalidate_i) perf_i_discard+=$countones(u_dut.u_icache.valid_q);
    if(u_dut.u_dcache.invalidate_i) perf_d_discard+=$countones(u_dut.u_dcache.valid_q);
  end
  // Opt-in integration diagnostics; never changes arbitration or handshakes.
  always @(negedge clk) if(rst_n && $test$plusargs("bus_debug") &&
      (u_dut.u_system.sram_axi.ar_valid || u_dut.u_system.sram_axi.aw_valid)) begin
    $display("BUSDBG t=%0t AR=%b/%b id=%h addr=%h len=%h size=%h burst=%h prot=%h cache=%h qos=%h lock=%b owner=%h AW=%b/%b addr=%h",
      $time,u_dut.u_system.sram_axi.ar_valid,u_dut.u_system.sram_axi.ar_ready,
      u_dut.u_system.sram_axi.ar_id,u_dut.u_system.sram_axi.ar_addr,
      u_dut.u_system.sram_axi.ar_len,u_dut.u_system.sram_axi.ar_size,
      u_dut.u_system.sram_axi.ar_burst,u_dut.u_system.sram_axi.ar_prot,
      u_dut.u_system.sram_axi.ar_cache,u_dut.u_system.sram_axi.ar_qos,
      u_dut.u_system.u_main_xbar.ar_locked_q[0],u_dut.u_system.u_main_xbar.ar_owner[0],
      u_dut.u_system.sram_axi.aw_valid,u_dut.u_system.sram_axi.aw_ready,
      u_dut.u_system.sram_axi.aw_addr);
    $display("BUSIN I=%b/%b id=%h addr=%h D=%b/%b id=%h addr=%h H=%b/%b id=%h addr=%h",
      u_dut.i_axi.ar_valid,u_dut.i_axi.ar_ready,u_dut.i_axi.ar_id,u_dut.i_axi.ar_addr,
      u_dut.d_axi.ar_valid,u_dut.d_axi.ar_ready,u_dut.d_axi.ar_id,u_dut.d_axi.ar_addr,
      host_axi.ar_valid,host_axi.ar_ready,host_axi.ar_id,host_axi.ar_addr);
  end
  logic [1:0] trace_mem_valid;
  logic [1:0][XLEN-1:0] trace_mem_addr;
  logic [1:0][63:0] trace_mem_wdata;
  assign external_irq = (flags[8] && !flags[9]) ? 31'd1 : 31'd0;
  rv23_soc_top #(.XLEN(XLEN),.HAS_V(HAS_V),.HAS_H(HAS_H),.HAS_ZAWRS(HAS_ZAWRS),.HAS_ZIMOP(HAS_ZIMOP),.HAS_ZCMOP(HAS_ZCMOP),.HAS_ZCB(HAS_ZCB),.HAS_SVINVAL(HAS_SVINVAL),.HAS_SSNPM(HAS_SSNPM),.HAS_D(HAS_D),.HAS_ZFHMIN(HAS_ZFHMIN),.HAS_ZFA(HAS_ZFA),.HAS_MISALIGNED(HAS_MISALIGNED),.HAS_CBO(HAS_CBO),.HAS_A(HAS_A),.HAS_B(HAS_B),.HAS_SMODE(HAS_SMODE),.HAS_MMU(HAS_MMU),.HAS_ZICOND(HAS_ZICOND),.RESET_VECTOR(XLEN'('h1000)),
    .BOOTROM_INIT_FILE(XLEN==64 ? "tb/fixtures/bootrom/bootrom_host_jump64.hex":
      "tb/fixtures/bootrom/bootrom_host_jump.hex")) u_dut (
    .clk_i(clk),.rst_ni(rst_n),.core_run_i(1'b1),.external_irq_i(external_irq),
    .debug_axi_s(host_axi),.debug_halt_req_i(halt),.debug_halted_o(halted),
    .soc_ready_o(soc_ready),.host_boot_entry_o(entry),.host_boot_flags_o(flags),
    .host_event_valid_o(event_valid),.host_event_ready_i(event_ready),
    .host_event_kind_o(event_kind),.host_event_data_o(event_data),
    .trace_valid_o(trace_valid),.trace_pc_o(trace_pc),.trace_instr_o(trace_instr),
    .trace_rd_o(trace_rd),.trace_rd_write_o(trace_we),.trace_rd_fp_o(trace_fp),
    .trace_rd_wdata_o(trace_data),.trace_trap_o(trace_trap),
    .trace_cause_o(trace_cause),.trace_tval_o(trace_tval));
  rv_host_dpi #(.HTIF_ENABLE(1),.ITIM_BASE_ADDR(32'h80000000),
    .ITIM_SIZE_BYTES(128*1024),.DTIM_BASE_ADDR(32'h80020000),.DTIM_SIZE_BYTES(896*1024),
    .HOSTIF_BOOT_ENTRY_OFFSET(HOSTIF_BOOT_ENTRY_OFF),
    .HOSTIF_BOOT_FLAGS_OFFSET(HOSTIF_BOOT_FLAGS_OFF)) u_host (
    .clk_i(clk),.rst_ni(rst_n),.soc_ready_i(soc_ready),.boot_wait_i(boot_wait),
    .host_axi_m(host_axi),.host_event_valid_i(event_valid),.host_event_ready_o(event_ready),
    .host_event_kind_i(event_kind),.host_event_data_i(event_data),
    .load_done_o(load_done),.load_failed_o(load_failed),
    .htif_exit_valid_o(htif_exit),.htif_exit_code_o(htif_code));
  rv_commit_trace_logger #(.XLEN(XLEN)) trace_logger (
    .clk_i(clk),.rst_ni(rst_n),.trace_valid_i(trace_valid),.trace_pc_i(trace_pc),
    .trace_instr_i(trace_instr),.trace_rd_i(trace_rd),.trace_rd_write_i(trace_we),
    .trace_rd_fp_i(trace_fp),.trace_rd_wdata_i(trace_data),.trace_trap_i(trace_trap),
    .trace_cause_i(trace_cause),.trace_tval_i(trace_tval),
    .trace_mem_valid_i(trace_mem_valid),.trace_mem_addr_i(trace_mem_addr),
    .trace_mem_wdata_i(trace_mem_wdata),
    .csr_commit_valid_i(u_dut.u_core.u_backend.csr_commit &&
      u_dut.u_core.u_backend.u_csr_file.csr_pending_q),
    .csr_commit_write_i(u_dut.u_core.u_backend.u_csr_file.csr_pending_write_q),
    .csr_commit_addr_i(u_dut.u_core.u_backend.u_csr_file.csr_pending_addr_q),
    .csr_commit_wdata_i(u_dut.u_core.u_backend.u_csr_file.csr_pending_wdata_q));
  always_comb begin
    trace_mem_valid='0;trace_mem_addr='0;trace_mem_wdata='0;
    for(int lane=0;lane<2;lane++) if(trace_valid[lane]) begin
      if(u_dut.u_core.u_backend.retire_is_load[lane]) begin
        trace_mem_valid[lane]=1;
        trace_mem_addr[lane]=u_dut.u_core.u_backend.u_lsu_cluster.u_lsq.lq_address_q[
          u_dut.u_core.u_backend.retire_lq_index[lane]];
      end else if(u_dut.u_core.u_backend.retire_is_store[lane]) begin
        trace_mem_valid[lane]=1;
        trace_mem_addr[lane]=u_dut.u_core.u_backend.u_lsu_cluster.u_lsq.sq_address_q[
          u_dut.u_core.u_backend.retire_sq_index[lane]];
        trace_mem_wdata[lane]=u_dut.u_core.u_backend.u_lsu_cluster.u_lsq.sq_data_q[
          u_dut.u_core.u_backend.retire_sq_index[lane]];
      end
    end
  end
  always @(posedge clk) if(rst_n) begin
    commits<=commits+int'(trace_valid[0])+int'(trace_valid[1]);
    for(int lane=0;lane<2;lane++) if(trace_valid[lane] &&
      trace_instr[lane]==32'h10500073 && trace_pc[lane]<32'h2000) boot_wait<=1;
    if(load_failed) $fatal(1,"ELF host/load transaction failed");
  end
  task automatic finish_test(input int code);
    int before_count;
    logic [63:0] value;
    if(code!=expected_exit_code) $fatal(1,"ELF reported failure exit code %0d",code);
    // Plain HostIF has stopped loading and owns no request after EXIT.
    if($test$plusargs("debug_check")) begin
      @(negedge clk);halt=1;wait(halted);
      repeat(8) begin @(negedge clk);if(!halted || trace_valid!=0)
        $fatal(1,"Unstable native debug halt");end
      u_host.axi_read64(32'h800f0000,value);
      if(value!==64'h0000000051a7c0de) $fatal(1,"Debug AXI read while halted: %h",value);
      u_host.write_register32(32'h800f0004,32'h1234abcd);
      u_host.axi_read64(32'h800f0000,value);
      if(value!==64'h1234abcd51a7c0de) $fatal(1,"Debug AXI write/read while halted");
      before_count=commits;@(negedge clk);halt=0;wait(commits>before_count);
      $display("NATIVE DEBUG PASS halt/drain/read/write/resume");
    end
    repeat(10) @(negedge clk);
    $display("CACHE_PERF i_hit=%0d i_miss=%0d d_hit=%0d d_miss=%0d snoops=%0d full_i_discard=%0d full_d_discard=%0d",
      perf_i_hit,perf_i_miss,perf_d_hit,perf_d_miss,perf_snoops,perf_i_discard,perf_d_discard);
    $display("PATH_PERF i_engine=%0d d_write_engine=%0d d_read_engine=%0d dual_d_hit=%0d if_backpressure=%0d",
      perf_i_engine,perf_d_write,perf_d_fill,perf_dual_d,perf_if_wait);
    $display("PASS rv32_program_tb commits=%0d",commits);$finish;
  endtask
  initial begin
    void'($value$plusargs("timeout_cycles=%d",timeout_cycles));
    void'($value$plusargs("expected_exit_code=%d",expected_exit_code));
    repeat(4) @(negedge clk);rst_n=1;
    repeat(timeout_cycles) @(posedge clk);
    $fatal(1,"ELF watchdog commits=%0d PC=%h ROB=%0d IQ=%0d",commits,trace_pc,
      u_dut.u_core.u_backend.rob_count,u_dut.u_core.u_backend.iq_count);
  end
  initial begin
    wait(rst_n);
    forever begin
      @(negedge clk);
      if(!finished && event_valid && event_ready && event_kind==HOST_EVENT_EXIT) begin
        finished=1;finish_test(int'(event_data));
      end
      if(!finished && htif_exit) begin finished=1;finish_test(int'(htif_code));end
    end
  end
  // Optional native observation; disabled for ordinary ISA/benchmark runs.
  bit vector_cache_observe;
  int vec_cache_reads=0,vec_cache_writes=0,vec_cache_hits=0,vec_cache_data_beats=0;
  initial vector_cache_observe=$test$plusargs("vector_cache_trace");
  always @(posedge clk)if(vector_cache_observe && rst_n && load_done)begin
    if(u_dut.u_core.u_backend.vector_active_q && u_dut.cbo_bus.req_valid && u_dut.cbo_bus.req_ready)begin
      if(!u_dut.cbo_memory_use_dcache || u_dut.cbo_direct_bus.req_valid)
        $fatal(1,"Vector data request bypassed shared D-cache");
      if(u_dut.cbo_bus.req_write)vec_cache_writes++;
      else begin
        vec_cache_reads++;
        if(u_dut.u_dcache.hit[0])vec_cache_hits++;
      end
    end
    if(u_dut.u_core.u_backend.vector_active_q && u_dut.d_normal_axi.ar_valid && u_dut.d_normal_axi.ar_ready &&
       u_dut.d_normal_axi.ar_addr>=32'h800a0000 && u_dut.d_normal_axi.ar_addr<32'h800a0080)
      vec_cache_data_beats++;
  end
  final if(vector_cache_observe)
    $display("VECTOR_CACHE reads=%0d writes=%0d hits=%0d data_read_beats=%0d",
      vec_cache_reads,vec_cache_writes,vec_cache_hits,vec_cache_data_beats);
endmodule

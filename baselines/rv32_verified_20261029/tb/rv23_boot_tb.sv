`timescale 1ns/1ps
module rv23_boot_tb;
  logic clk_i=0,rst_ni=0,core_run=0,halt=0,halted;
  always #5 clk_i=~clk_i;
  rv_axi4_if #(.ID_WIDTH(4)) dbg (.clk_i,.rst_ni);
  logic [1:0] tv,tt;
  logic [1:0][31:0] pc;
  logic [1:0][31:0] instruction;
  integer commits=0,fences=0;
  logic msip,mtip,meip;
  rv23_soc_top #(.SRAM_INIT_FILE("out/boot.hex")) dut (
    .clk_i,.rst_ni,.core_run_i(core_run),.external_irq_i('0),
    .debug_halt_req_i(halt),.debug_halted_o(halted),.debug_axi_s(dbg),
    .host_event_ready_i(1'b1),.trace_valid_o(tv),.trace_trap_o(tt),
    .trace_pc_o(pc),.trace_instr_o(instruction),
    .irq_software_o(msip),.irq_timer_o(mtip),.irq_external_o(meip));
  always @(posedge clk_i) if(rst_ni && core_run) begin
    commits<=commits+int'(tv[0])+int'(tv[1]);
    for(int n=0;n<2;n++) if(tv[n]) begin
      if(tt[n]) $fatal(1,"Unexpected boot trap PC=%h instruction=%h",pc[n],instruction[n]);
    end
    if(dut.fence_i) fences<=fences+1;
  end
  initial begin
    dbg.aw_id=0;dbg.aw_addr=0;dbg.aw_len=0;dbg.aw_size=3;dbg.aw_burst=1;
    dbg.aw_prot=0;dbg.aw_cache=0;dbg.aw_qos=0;dbg.aw_valid=0;
    dbg.w_data=0;dbg.w_strb=0;dbg.w_last=1;dbg.w_valid=0;dbg.b_ready=1;
    dbg.ar_id=0;dbg.ar_addr=0;dbg.ar_len=0;dbg.ar_size=3;dbg.ar_burst=1;
    dbg.ar_prot=0;dbg.ar_cache=0;dbg.ar_qos=0;dbg.ar_valid=0;dbg.r_ready=1;
    repeat(4) @(negedge clk_i);rst_ni=1;
    repeat(4) @(negedge clk_i);core_run=1;
    wait((dut.u_system.u_sram.u_mem.mem[`DONE_ROW] >> `DONE_SHIFT) == 64'h600d);
    @(negedge clk_i);halt=1;
    wait(halted);
    if(fences!=1 || commits<15 || msip) $fatal(1,"Boot/halt status");
    repeat(10) begin
      @(negedge clk_i);
      if(tv!=0 || !halted) $fatal(1,"Core did not remain drained under halt trace=%b halted=%b core=%b arb=%b icache=%b dcache=%b IFstate=%0d",
        tv,halted,dut.core_drained,dut.arb_idle,dut.i_idle,dut.d_idle,dut.u_if_adapter.active_q);
    end
    begin
      int count_before_resume;
      count_before_resume=commits;halt=0;
      wait(commits>count_before_resume);
    end
    $display("PASS rv23_boot_tb RV32 load/store, FENCE.I, CLINT, halt/drain/resume; commits=%0d",commits);
    $finish;
  end
  initial begin #2000000; $fatal(1,"Boot watchdog"); end
endmodule

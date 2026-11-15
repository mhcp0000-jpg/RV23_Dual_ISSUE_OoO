`timescale 1ns/1ps
module rv23_ptw_debug_coherence_tb;
  import rv_soc_pkg::*;
  localparam logic [31:0] PTE_ADDR=32'h80022000;
  localparam logic [63:0] PTE_A=64'h2000c0c7, PTE_B=64'h2000c4c7;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();
  int updates=0, pte_responses=0, pte_hits=0, resident_snoops=0;
  int halted_updates=0, running_updates=0;
  bit pte_pending=0;

  always @(posedge core.clk) if (core.rst_n && core.load_done) begin
    if (core.u_dut.ptw_bus.req_valid && core.u_dut.ptw_bus.req_ready &&
        core.u_dut.ptw_bus.req_addr==PTE_ADDR) begin
      if (pte_pending) $fatal(1,"Overlapping PTE ownership");
      pte_pending=1;
    end
    // The share arbiter captures the PTW request before presenting it to the
    // cache. Count the downstream handshake with the captured PTW owner.
    if (core.u_dut.u_dcache.hit_accept[1] &&
        core.u_dut.u_dcache.req_addr[1]==PTE_ADDR &&
        core.u_dut.g_ptw_port.u_share.owner_q) pte_hits++;
    if (pte_pending && core.u_dut.ptw_bus.rsp_valid && core.u_dut.ptw_bus.rsp_ready) begin
      if (core.u_dut.ptw_bus.rsp_rdata!==(updates[0]?PTE_B:PTE_A))
        $fatal(1,"Stale PTE response after update %0d: %h",updates,core.u_dut.ptw_bus.rsp_rdata);
      pte_pending=0; pte_responses++;
    end
    if (core.u_dut.sram_write_snoop && core.u_dut.sram_write_snoop_addr==PTE_ADDR &&
        core.u_dut.u_dcache.snoop_resident) resident_snoops++;
  end

  initial begin
    wait(core.load_done);
    for (int phase=1;phase<=16;phase++) begin
      bit halt_this;
      halt_this=phase%4 inside {0,1};
      do @(negedge core.clk); while (!(core.event_valid && core.event_ready &&
        core.event_kind==HOST_EVENT_TOHOST && core.event_data==(32'h50540000|32'(phase))));
      if (halt_this) begin
        core.halt=1;
        wait(core.halted);
        halted_updates++;
      end else begin
        if (core.halted) $fatal(1,"Core unexpectedly halted during live update");
        running_updates++;
      end
      // The update must exercise a resident line, not an empty-cache refill.
      if (!core.u_dut.u_dcache.valid_q[PTE_ADDR[14:6]] ||
          core.u_dut.u_dcache.tags[PTE_ADDR[14:6]]!=PTE_ADDR[31:15])
        $fatal(1,"Missing resident PTE before debug write phase %0d",phase);
      if (phase[0]) core.u_host.write_register64(PTE_ADDR,PTE_B);
      else core.u_host.write_register32(PTE_ADDR,PTE_A[31:0]);
      updates=phase;
      core.u_host.write_register64(32'h80033f00,64'(phase));
      @(negedge core.clk); core.halt=0;
    end
  end
  always @(negedge core.clk) if (core.event_valid && core.event_ready &&
      core.event_kind==HOST_EVENT_EXIT && core.event_data==0) begin
    // The initial translation is a cold miss; all 16 subsequent remaps hit.
    if (updates!=16 || pte_responses<17 || pte_hits<16 || resident_snoops<16 ||
        halted_updates!=8 || running_updates!=8)
      $fatal(1,"Missing coherence coverage updates=%0d pte=%0d hits=%0d snoops=%0d",
             updates,pte_responses,pte_hits,resident_snoops);
    $display("PTW DEBUG COHERENCE PASS updates=%0d pte_responses=%0d pte_hits=%0d resident_snoops=%0d",
             updates,pte_responses,pte_hits,resident_snoops);
    $display("PTW DEBUG MODES halted=%0d running=%0d",halted_updates,running_updates);
  end
endmodule

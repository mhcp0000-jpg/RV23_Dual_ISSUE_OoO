`timescale 1ns/1ps
module rv23_wrs_debug_wake_tb;
  import rv_soc_pkg::*;
  localparam logic [31:0] RESERVED=32'h80070000;
  localparam logic [31:0] SAME_LINE=RESERVED+8, NEXT_LINE=RESERVED+64;
  localparam logic [31:0] MAILBOX=RESERVED+128;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();

  wire waiting = core.u_dut.u_core.u_backend.u_wrs.request_valid_i;
  wire complete = core.u_dut.u_core.u_backend.wrs_complete;
  wire reserved = core.u_dut.u_atomic.reservation_valid_o;
  wire snoop = core.u_dut.sram_write_snoop;
  wire [31:0] snoop_address = core.u_dut.sram_write_snoop_addr;
  int same_line_wakes=0, unrelated_writes=0;
  int atomic_phase=0, adjacent_sc=0, overlapping_sc=0;
  bit checking=0;

  always @(posedge core.clk) if (checking && snoop) begin
    case (snoop_address)
      NEXT_LINE: begin
        if (!waiting || complete || !reserved) $fatal(1,"Unrelated AXI write ended WRS");
        unrelated_writes++;
      end
      SAME_LINE: begin
        if (!waiting || !complete || reserved || core.halt || core.halted)
          $fatal(1,"Same-line AXI write did not wake WRS");
        same_line_wakes++;
      end
      default: $fatal(1,"Unexpected SRAM write during WRS");
    endcase
  end

  always @(posedge core.clk) if (atomic_phase!=0 && snoop) begin
    if (core.halt || core.halted) $fatal(1,"Core halted during LR/SC interference");
    case (snoop_address)
      NEXT_LINE: begin
        if (atomic_phase>6 || !reserved) $fatal(1,"Adjacent write invalidated reservation");
        adjacent_sc++;
      end
      RESERVED, RESERVED+4: begin
        if (atomic_phase<7 || reserved)
          $fatal(1,"Overlapping write did not invalidate reservation");
        overlapping_sc++;
      end
      default: $fatal(1,"Unexpected write between LR and SC");
    endcase
  end

  initial begin
    wait (core.load_done);
    for (int phase=1; phase<=4; phase++) begin
      do @(negedge core.clk); while (!waiting || complete || !reserved);
      checking=1;
      repeat (8) begin
        @(negedge core.clk);
        if (!waiting || complete || !reserved) $fatal(1,"WRS completed before debug writes");
      end
      core.u_host.write_register64(NEXT_LINE,64'hf000000000000000|64'(phase));
      repeat (8) begin
        @(negedge core.clk);
        if (!waiting || complete || !reserved) $fatal(1,"WRS did not retain the unrelated reservation");
      end
      if (phase<=2) core.u_host.write_register32(SAME_LINE,32'h13579abc);
      else core.u_host.write_register64(SAME_LINE,64'h1234567813579abc);
      if (same_line_wakes!=phase || unrelated_writes!=phase)
        $fatal(1,"Missing debug write witness at phase %0d",phase);
      checking=0;
      do @(negedge core.clk); while (waiting);
    end
    for (int phase=5; phase<=8; phase++) begin
      do @(negedge core.clk); while (!reserved);
      atomic_phase=phase;
      case (phase)
        5, 6: core.u_host.write_register64(NEXT_LINE,64'hcafef00dbeefface);
        7: core.u_host.write_register32(RESERVED,32'h2468ace0);
        8: core.u_host.write_register32(RESERVED+4,32'h2468ace0);
      endcase
      atomic_phase=0;
      core.u_host.write_register64(MAILBOX,64'(phase));
      if (phase<=6)
        do @(negedge core.clk); while (reserved);
    end
  end

  always @(negedge core.clk) if (core.event_valid && core.event_ready &&
      core.event_kind==HOST_EVENT_EXIT && core.event_data==0) begin
    if (same_line_wakes!=4 || unrelated_writes!=4)
      $fatal(1,"Incomplete WRS wake test");
    if (adjacent_sc!=2 || overlapping_sc!=2)
      $fatal(1,"Incomplete LR/SC interference test");
    $display("WRS DEBUG WAKE PASS same_line=4 unrelated=4");
    $display("LRSC DEBUG INTERFERENCE PASS adjacent=2 overlapping=2");
  end
endmodule


`timescale 1ns/1ps
module rv23_vector_irq_tb;
  localparam logic [31:0] VECTOR_BASE = 32'h800a0000;
  localparam logic [31:0] SCALAR_ADDRESS = 32'h800a0100;
  localparam logic [31:0] PLIC_ENABLE = 32'h0c002000;
  localparam logic [31:0] PLIC_CLAIM = 32'h0c200004;
  localparam int VECTOR_BYTES = 128;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();

  wire vector_active = core.u_dut.u_core.u_backend.vector_active_q;
  wire vector_write = vector_active && core.u_dut.u_core.u_backend.vector_memory_valid &&
    core.u_dut.u_core.u_backend.vector_memory_write && core.u_dut.u_core.u_backend.cbo_write_ready_i;
  wire [31:0] vector_address = core.u_dut.u_core.u_backend.vector_memory_address;
  wire irq_pending = core.u_dut.u_core.u_backend.csr_interrupt_pending;
  wire irq_accept = core.u_dut.u_core.u_backend.csr_trap_valid &&
    core.u_dut.u_core.u_backend.csr_trap_ready &&
    core.u_dut.u_core.u_backend.csr_trap_is_interrupt;
  int unsigned cycle = 0, writes = 0;
  int unsigned first_write = 0, pending = 0, pending_bytes = 0, last_write = 0;
  int unsigned retired = 0, trap = 0, scalar_write = 0;
  int unsigned enable_writes = 0, vector_claims = 0, scalar_claims = 0;

  initial begin
    wait(writes == 1);
    @(negedge core.clk);
    force core.external_irq = 31'd1;
    wait(trap != 0);
    @(negedge core.clk);
    release core.external_irq;
    wait(enable_writes == 2);
    @(negedge core.clk);
    force core.external_irq = 31'h0000000e;
    repeat (2) @(negedge core.clk);
    release core.external_irq;
  end

  always @(posedge core.clk) if (core.rst_n && core.load_done) begin
    cycle++;
    if (core.u_dut.u_system.plic_axi.aw_valid && core.u_dut.u_system.plic_axi.aw_ready &&
        core.u_dut.u_system.plic_axi.aw_addr == PLIC_ENABLE)
      enable_writes++;
    if (enable_writes == 2 && core.u_dut.u_system.plic_axi.ar_valid &&
        core.u_dut.u_system.plic_axi.ar_ready && core.u_dut.u_system.plic_axi.ar_addr == PLIC_CLAIM) begin
      if (vector_active) begin
        if (scalar_claims != 0) $fatal(1,"Scalar claim bypassed an ordered vector claim");
        vector_claims++;
      end else begin
        if (vector_claims != 2) $fatal(1,"Expected two active vector claim requests");
        scalar_claims++;
      end
    end
    if (vector_write) begin
      if (vector_address != VECTOR_BASE + writes || writes >= VECTOR_BYTES)
        $fatal(1,"Unexpected vector write address %h at byte %0d", vector_address, writes);
      if (writes == 0) first_write = cycle;
      writes++;
      if (writes == VECTOR_BYTES) last_write = cycle;
    end
    if (irq_pending && pending == 0) begin
      if (!vector_active || writes == 0 || writes >= VECTOR_BYTES)
        $fatal(1,"Interrupt did not reach the core during the vector store");
      pending = cycle;
      pending_bytes = writes;
    end
    for (int lane = 0; lane < 2; lane++) begin
      if (core.trace_valid[lane] && !core.trace_trap[lane] && core.trace_instr[lane] == 32'h02040427) begin
        if (writes != VECTOR_BYTES || retired != 0)
          $fatal(1,"Vector store retired without all bytes or retired twice");
        retired = cycle;
      end
    end
    if (irq_accept) begin
      if (trap != 0 || pending == 0 || retired == 0 || retired >= cycle || vector_active ||
          core.u_dut.u_core.u_backend.csr_trap_cause != 6'd11)
        $fatal(1,"External interrupt delivered at an imprecise boundary");
      trap = cycle;
    end
    if (core.u_dut.sram_write_snoop && core.u_dut.sram_write_snoop_addr == SCALAR_ADDRESS &&
        core.u_dut.sram_write_snoop_data != 0) begin
      if (scalar_write != 0 || writes != VECTOR_BYTES)
        $fatal(1,"Following scalar write reordered or duplicated");
      scalar_write = cycle;
    end
  end

  final begin
    if (trap == 0 || scalar_write == 0) $error("Missing vector IRQ or following scalar write");
    if (vector_claims != 2 || scalar_claims != 2) $error("Missing PLIC claim request");
    $display("VECTOR IRQ first=%0d pending=%0d pending_bytes=%0d last=%0d retire=%0d trap=%0d scalar=%0d",
             first_write,pending,pending_bytes,last_write,retired,trap,scalar_write);
    $display("PLIC CLAIM ORDER vector=%0d scalar=%0d", vector_claims, scalar_claims);
  end
endmodule

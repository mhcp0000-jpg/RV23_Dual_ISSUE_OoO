`timescale 1ns/1ps
module rv23_vector_scalar_irq_tb;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();
`define B core.u_dut.u_core.u_backend
  logic [63:0] irq_pc;
  int cycle=0,started=0,pending=0,retired=0,trapped=0,overlap=0;
  wire active=`B.vector_active_q && `B.rob_head_pc==irq_pc;
  wire interrupt_accept=`B.csr_trap_valid && `B.csr_trap_ready && `B.csr_trap_is_interrupt;
  initial begin
    if(!$value$plusargs("irq_pc=%h",irq_pc))$fatal(1,"Missing IRQ vector PC");
    wait(active);
    @(negedge core.clk);
    force core.external_irq=31'd1;
    wait(interrupt_accept);
    @(negedge core.clk);
    release core.external_irq;
  end
  always @(posedge core.clk)if(core.rst_n && core.load_done)begin
    cycle++;
    if(active)begin
      if(started==0)started=cycle;
      if(`B.csr_interrupt_pending && pending==0)pending=cycle;
      for(int p=0;p<2;p++)
        if(`B.fast_req_valid[p] && `B.fast_req_ready[p] &&
           `B.sequence_after_backend(`B.fast_req_sequence[p],`B.rob_head_sequence))overlap++;
    end
    for(int p=0;p<2;p++)if(core.trace_valid[p] && core.trace_pc[p]==irq_pc)retired=cycle;
    if(interrupt_accept)begin
      trapped=cycle;
      if(retired==0 || active)$fatal(1,"Interrupt accepted before non-memory vector completed");
    end
  end
  final begin
    $display("VECTOR_SCALAR_IRQ start=%0d pending=%0d retire=%0d trap=%0d overlap=%0d",
      started,pending,retired,trapped,overlap);
    if(!(started<pending && pending<retired && retired<trapped && overlap>0))
      $error("Missing non-memory vector/scalar IRQ boundary witness");
  end
`undef B
endmodule

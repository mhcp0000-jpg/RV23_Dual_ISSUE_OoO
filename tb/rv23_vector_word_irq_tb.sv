`timescale 1ns/1ps
module rv23_vector_word_irq_tb;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();
`define B core.u_dut.u_core.u_backend
`define V core.u_dut.u_core.u_backend.g_vector_head.u_head
  logic [63:0] irq_pc;
  int cycle=0,first=0,pending=0,last_rf=0,retired=0,trapped=0,scalar_write=0;
  int reads=0,responses=0,writes=0,refills=0,pending_reads=0;
  wire active=`B.vector_active_q && `B.rob_head_pc==irq_pc;
  wire interrupt_accept=`B.csr_trap_valid && `B.csr_trap_ready && `B.csr_trap_is_interrupt;
  initial begin
    if(!$value$plusargs("irq_pc=%h",irq_pc))$fatal(1,"Missing load PC");
    wait(reads==1);
    @(negedge core.clk);force core.external_irq=31'd1;
    wait(trapped!=0);
    @(negedge core.clk);release core.external_irq;
  end
  always @(posedge core.clk)if(core.rst_n && core.load_done)begin
    cycle++;
    if(active)begin
      if(`V.memory_valid_o && `V.memory_ready_i)begin
        if(`V.memory_write_o || !`V.u_memory.coalesced_q || `V.memory_size_o!=3 ||
           `V.memory_address_o!=32'h800a0000+32'(reads*8) || reads>=16)
          $fatal(1,"Expected sixteen complete SRAM word reads");
        if(reads==0)first=cycle;
        reads++;
      end
      if(`V.memory_response_valid_i && `V.memory_response_ready_o)responses++;
      if(`V.rf_write_q)begin
        if(!`V.rf_packed_q || `V.rf_bit_mask_q!={64'b0,64'hffffffffffffffff})
          $fatal(1,"Expected a registered packed word write");
        writes++;last_rf=cycle;
      end
      if(core.u_dut.d_normal_axi.ar_valid && core.u_dut.d_normal_axi.ar_ready &&
         core.u_dut.d_normal_axi.ar_addr>=32'h800a0000 && core.u_dut.d_normal_axi.ar_addr<32'h800a0080)
        refills++;
      if(`B.csr_interrupt_pending && pending==0)begin
        if(reads==0 || reads>=16)$fatal(1,"IRQ missed active word-load interval");
        pending=cycle;pending_reads=reads;
      end
    end
    for(int p=0;p<2;p++)if(core.trace_valid[p] && !core.trace_trap[p] && core.trace_pc[p]==irq_pc)begin
      if(retired!=0 || reads!=16 || responses!=16 || writes!=16 || last_rf>=cycle)
        $fatal(1,"Load retired before its final RF word");
      retired=cycle;
    end
    if(interrupt_accept)begin
      if(trapped!=0 || retired==0 || retired>=cycle || active || `B.csr_trap_cause!=11)
        $fatal(1,"Imprecise word-load interrupt");
      trapped=cycle;
    end
    if(core.u_dut.sram_write_snoop && core.u_dut.sram_write_snoop_addr==32'h800a0100 &&
       core.u_dut.sram_write_snoop_data!=0)begin
      if(scalar_write!=0 || retired==0 || last_rf>=cycle)$fatal(1,"Younger scalar store escaped load ordering");
      scalar_write=cycle;
    end
  end
  final begin
    if(!(first<pending && pending<last_rf && last_rf<retired && retired<trapped && scalar_write>retired))
      $error("Missing precise word-load IRQ witness");
    $display("WORD_IRQ first=%0d pending=%0d pending_reads=%0d last_rf=%0d retire=%0d trap=%0d scalar=%0d reads=%0d responses=%0d writes=%0d refills=%0d",
      first,pending,pending_reads,last_rf,retired,trapped,scalar_write,reads,responses,writes,refills);
  end
`undef V
`undef B
endmodule

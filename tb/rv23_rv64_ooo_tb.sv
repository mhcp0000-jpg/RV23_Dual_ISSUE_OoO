`timescale 1ns/1ps
module rv23_rv64_ooo_tb;
  import rv_soc_pkg::*;
  import rv_ooo_pkg::*;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();
  logic [63:0] div_pc,dep_pc,first_pc,end_pc;
  logic [(1<<ROB_SEQ_WIDTH)-1:0] measured_sequences='0;
  logic [63:0] sequence_pc[0:(1<<ROB_SEQ_WIDTH)-1];
  longint unsigned cycles=0, div_issue=0, dep_issue=0, first_young_issue=0;
  logic [63:0] next_retire;
  localparam logic [31:0] BANK_BASE = 32'h80020000;
  int instruction_pairs=0, data_pairs=0, sram_reads=0;
  bit instruction_pair_pending=0, data_pair_pending=0;
  logic [1:0][31:0] data_pair_addresses;
  int dual_issue=0,dual_execute=0,dual_retire=0,young_bypass=0,retired=0,issued=0;
  int fd;
  string filename;
  bit done=0;
  function automatic bit in_region(input logic [63:0] pc);
    return pc>=div_pc && pc<end_pc;
  endfunction
  function automatic bit in_young(input logic [63:0] pc);
    return pc>=first_pc && pc<end_pc;
  endfunction
  initial begin
    if (!$value$plusargs("ooo_div_pc=%h",div_pc) ||
        !$value$plusargs("ooo_dep_pc=%h",dep_pc) ||
        !$value$plusargs("ooo_first_pc=%h",first_pc) ||
        !$value$plusargs("ooo_end_pc=%h",end_pc) ||
        !$value$plusargs("ooo_trace=%s",filename)) $fatal(1,"Missing OoO fixture inputs");
    if (dep_pc!=div_pc+4 || first_pc!=dep_pc+4 || end_pc!=first_pc+32 ||
        !CORE_CFG_INT_ISSUE_PIPELINE) $fatal(1,"Unexpected production/fixture geometry");
    if ($bits(core.u_dut.d_axi.w_data)!=64 || $bits(core.u_dut.i_axi.r_data)!=64 ||
        $bits(core.u_dut.u_system.sram_axi.r_data)!=64 ||
        core.u_dut.u_system.u_sram.SIZE_KB!=1024 ||
        $bits(core.u_dut.u_icache.data_bank0)!=131072 ||
        $bits(core.u_dut.u_icache.data_bank1)!=131072 ||
        $bits(core.u_dut.u_dcache.data_bank0)!=131072 ||
        $bits(core.u_dut.u_dcache.data_bank1)!=131072)
      $fatal(1,"Unexpected SRAM, AXI or L1 geometry");
    next_retire=div_pc;
    fd=$fopen(filename,"w");
    if (!fd) $fatal(1,"Cannot open pipeline observation CSV");
    $fdisplay(fd,"cycle,event,pc,sequence,lane");
  end
  always @(posedge core.clk) if (core.rst_n && core.load_done && !done) begin
    cycles++;
    if (core.u_dut.u_system.sram_axi.ar_valid && core.u_dut.u_system.sram_axi.ar_ready &&
        core.u_dut.u_system.sram_axi.ar_addr[31:6] == BANK_BASE[31:6]) begin
      if (core.u_dut.u_system.sram_axi.ar_size!=3) $fatal(1,"Non-64-bit refill beat");
      sram_reads++;
    end
    if (instruction_pair_pending) begin
      if (!(&core.u_dut.u_icache.response_valid_q)) $fatal(1,"Missing next-cycle I-cache bank pair");
      instruction_pairs++;
    end
    instruction_pair_pending = (&core.u_dut.u_icache.hit_accept) &&
      (&core.u_dut.u_icache.bank_read_en) &&
      (core.u_dut.u_icache.req_addr[0][31:4] == core.u_dut.u_icache.req_addr[1][31:4]);
    if (data_pair_pending) begin
      if (!(&core.u_dut.u_dcache.response_valid_q)) $fatal(1,"Missing next-cycle D-cache bank pair");
      data_pairs++;
      $display("RV64 D BANK PAIR accept=%0d response=%0d addr=%08h/%08h data=%016h/%016h",
        cycles-1, cycles, data_pair_addresses[0], data_pair_addresses[1],
        core.u_dut.u_dcache.response_data_q[0], core.u_dut.u_dcache.response_data_q[1]);
    end
    data_pair_pending = (&core.u_dut.u_dcache.hit_accept) && (&core.u_dut.u_dcache.bank_read_en) &&
      core.u_dut.u_dcache.req_addr[0][31:4] == BANK_BASE[31:4] &&
      core.u_dut.u_dcache.req_addr[1][31:4] == BANK_BASE[31:4];
    if (data_pair_pending) data_pair_addresses=core.u_dut.u_dcache.req_addr;
    if (!core.u_dut.u_core.u_backend.flush_valid) begin
      for (int c=0;c<2;c++) if (core.u_dut.u_core.u_backend.cand_grant[c] &&
          in_region(core.u_dut.u_core.u_backend.cand_pc[c])) begin
        logic [63:0] pc;
        pc=core.u_dut.u_core.u_backend.cand_pc[c];
        measured_sequences[core.u_dut.u_core.u_backend.cand_sequence[c]]=1;
        sequence_pc[core.u_dut.u_core.u_backend.cand_sequence[c]]=pc;
        issued++;
        $fdisplay(fd,"%0d,issue,%h,%0d,%0d",cycles,pc,
          core.u_dut.u_core.u_backend.cand_sequence[c],core.u_dut.u_core.u_backend.cand_grant_port[c]);
        if (pc==div_pc) div_issue=cycles;
        if (pc==dep_pc) dep_issue=cycles;
        if (in_young(pc)) begin
          if (first_young_issue==0) first_young_issue=cycles;
          if (dep_issue==0 && core.u_dut.u_core.u_backend.u_div.busy_q) young_bypass++;
        end
      end
      if (&core.u_dut.u_core.u_backend.cand_grant &&
          core.u_dut.u_core.u_backend.cand_fu[0]==FU_INT &&
          core.u_dut.u_core.u_backend.cand_fu[1]==FU_INT &&
          in_young(core.u_dut.u_core.u_backend.cand_pc[0]) &&
          in_young(core.u_dut.u_core.u_backend.cand_pc[1])) dual_issue++;
    end
    for (int lane=0;lane<2;lane++) if (core.u_dut.u_core.u_backend.int_issue_take[lane] &&
        measured_sequences[core.u_dut.u_core.u_backend.int_issue_q[lane].sequence_id])
      $fdisplay(fd,"%0d,execute,%h,%0d,%0d",cycles,
        sequence_pc[core.u_dut.u_core.u_backend.int_issue_q[lane].sequence_id],
        core.u_dut.u_core.u_backend.int_issue_q[lane].sequence_id,lane);
    if (&core.u_dut.u_core.u_backend.int_issue_take &&
        measured_sequences[core.u_dut.u_core.u_backend.int_issue_q[0].sequence_id] &&
        measured_sequences[core.u_dut.u_core.u_backend.int_issue_q[1].sequence_id]) dual_execute++;
    if (&core.trace_valid && in_region(core.trace_pc[0]) && in_region(core.trace_pc[1])) dual_retire++;
    for (int lane=0;lane<2;lane++) if (core.trace_valid[lane] && in_region(core.trace_pc[lane])) begin
      logic [ROB_SEQ_WIDTH-1:0] retired_sequence;
      retired_sequence=core.u_dut.u_core.u_backend.retire_sequence[lane];
      if (core.trace_trap[lane] || core.trace_pc[lane]!=next_retire ||
          !measured_sequences[retired_sequence] || sequence_pc[retired_sequence]!=next_retire)
        $fatal(1,"Out-of-order architectural retirement pc=%h expected=%h",core.trace_pc[lane],next_retire);
      $fdisplay(fd,"%0d,retire,%h,%0d,%0d",cycles,core.trace_pc[lane],retired_sequence,lane);
      measured_sequences[retired_sequence]=0;
      next_retire+=4;retired++;
    end
  end
  always @(negedge core.clk) if (!done && core.event_valid && core.event_ready &&
      core.event_kind==HOST_EVENT_EXIT && core.event_data==0) begin
    if (issued!=10 || retired!=10 || dual_issue==0 || dual_execute==0 || dual_retire==0 ||
        young_bypass==0 || div_issue==0 || first_young_issue<=div_issue ||
        first_young_issue>=dep_issue || next_retire!=end_pc)
      $fatal(1,"Missing RV64 OoO coverage issued=%0d retired=%0d dual=%0d/%0d/%0d bypass=%0d order=%0d/%0d/%0d",
        issued,retired,dual_issue,dual_execute,dual_retire,young_bypass,div_issue,first_young_issue,dep_issue);
    if (instruction_pairs==0 || data_pairs==0 || sram_reads==0)
      $fatal(1,"Missing simultaneous cache hits i_pairs=%0d d_pairs=%0d", instruction_pairs, data_pairs);
    $display("RV64 CACHE BANKS PASS i_pairs=%0d d_pairs=%0d sram_reads=%0d", instruction_pairs, data_pairs, sram_reads);
    $display("RV64 OOO PASS dual_issue=%0d dual_execute=%0d dual_retire=%0d young_bypass=%0d issue_cycles=%0d/%0d/%0d",
      dual_issue,dual_execute,dual_retire,young_bypass,div_issue,first_young_issue,dep_issue);
    $fclose(fd);done=1;
  end
endmodule

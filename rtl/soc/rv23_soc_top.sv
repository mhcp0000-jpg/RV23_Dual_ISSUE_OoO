// RVA23S64 implementation target. Mandatory V/H/D/S/MMU are not yet complete.
// XLEN32 remains an explicit regression configuration.
module rv23_soc_top #(
  parameter int unsigned XLEN = 64,
  parameter bit HAS_B = 1,
  parameter bit HAS_A=(XLEN==64),
  parameter bit HAS_CBO=(XLEN==64),
  parameter bit HAS_MISALIGNED=(XLEN==64),
  parameter bit HAS_V=(XLEN==64),
  parameter bit HAS_H=(XLEN==64),
  parameter bit HAS_D=(XLEN==64),HAS_ZFHMIN=(XLEN==64),HAS_ZFA=(XLEN==64),
  parameter bit HAS_SSNPM=(XLEN==64),
  parameter bit HAS_ZAWRS=(XLEN==64),HAS_ZIMOP=(XLEN==64),HAS_ZCMOP=(XLEN==64),HAS_ZCB=(XLEN==64),HAS_SVINVAL=(XLEN==64),
  parameter bit HAS_SMODE = 1,
  parameter bit HAS_MMU=(XLEN==64),
  parameter bit HAS_ZICOND = 1,
  parameter int unsigned CLOCK_HZ = 100_000_000,
  parameter int unsigned TIMEBASE_HZ = rv_soc_pkg::TIMEBASE_HZ,
  parameter int unsigned PLIC_NUM_SOURCES = rv_soc_pkg::PLIC_NUM_SOURCES,
  parameter string BOOTROM_INIT_FILE = "",
  parameter string SRAM_INIT_FILE = "",
  parameter logic [XLEN-1:0] RESET_VECTOR = XLEN'(rv23_pkg::SRAM_BASE),
  parameter logic [XLEN-1:0] TRAP_VECTOR = XLEN'(rv23_pkg::SRAM_BASE)
) (
  input logic clk_i, rst_ni,
  input logic core_run_i,
  input logic [PLIC_NUM_SOURCES-1:1] external_irq_i,
  input logic debug_halt_req_i,
  output logic debug_halted_o,
  rv_axi4_if.slave debug_axi_s,
  output logic soc_ready_o,
  output logic irq_software_o, irq_timer_o, irq_external_o,
  output logic [31:0] host_boot_entry_o, host_boot_flags_o,
  output logic host_event_valid_o,
  input logic host_event_ready_i,
  output rv_soc_pkg::host_event_e host_event_kind_o,
  output logic [31:0] host_event_data_o,
  output logic [1:0]                    trace_valid_o,
  output logic [1:0][XLEN-1:0]          trace_pc_o,
  output logic [1:0][31:0]              trace_instr_o,
  output logic [1:0][4:0]               trace_rd_o,
  output logic [1:0]                    trace_rd_write_o,
  output logic [1:0]                    trace_rd_fp_o,
  output logic [1:0][XLEN-1:0]          trace_rd_wdata_o,
  output logic [1:0]                    trace_trap_o,
  output logic [1:0][5:0]               trace_cause_o,
  output logic [1:0][XLEN-1:0]          trace_tval_o
);
  logic msip, mtip, meip, seip;
  logic [63:0] mtime;
  logic sram_write_snoop;
  logic [31:0] sram_write_snoop_addr;
  logic [63:0] sram_write_snoop_data;
  logic [7:0] sram_write_snoop_strb;
  rv_axi4_if #(.ID_WIDTH(4)) i_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) d_axi (.clk_i,.rst_ni);

  rv23_core #(
    .XLEN(XLEN), .HAS_B(HAS_B), .HAS_A(HAS_A), .HAS_CBO(HAS_CBO),
    .HAS_MISALIGNED(HAS_MISALIGNED), .HAS_V(HAS_V), .HAS_H(HAS_H), .HAS_D(HAS_D),
    .HAS_ZFHMIN(HAS_ZFHMIN), .HAS_ZFA(HAS_ZFA), .HAS_SSNPM(HAS_SSNPM), .HAS_ZAWRS(HAS_ZAWRS),
    .HAS_ZIMOP(HAS_ZIMOP), .HAS_ZCMOP(HAS_ZCMOP), .HAS_ZCB(HAS_ZCB), .HAS_SVINVAL(HAS_SVINVAL),
    .HAS_SMODE(HAS_SMODE), .HAS_MMU(HAS_MMU), .HAS_ZICOND(HAS_ZICOND), .RESET_VECTOR(RESET_VECTOR),
    .TRAP_VECTOR(TRAP_VECTOR)
  ) u_cached_core (
    .clk_i, .rst_ni, .core_run_i,
    .i_axi_m(i_axi), .d_axi_m(d_axi),
    .msip, .mtip, .meip, .seip, .mtime,
    .debug_halt_req_i, .debug_halted_o,
    .sram_write_snoop, .sram_write_snoop_addr,
    .sram_write_snoop_data, .sram_write_snoop_strb,
    .trace_valid_o, .trace_pc_o, .trace_instr_o, .trace_rd_o,
    .trace_rd_write_o, .trace_rd_fp_o, .trace_rd_wdata_o, .trace_trap_o,
    .trace_cause_o, .trace_tval_o
  );

  rv23_system_bus #(.CLOCK_HZ(CLOCK_HZ),.TIMEBASE_HZ(TIMEBASE_HZ),
    .PLIC_NUM_SOURCES(PLIC_NUM_SOURCES),.BOOTROM_INIT_FILE(BOOTROM_INIT_FILE),
    .SRAM_INIT_FILE(SRAM_INIT_FILE),.HAS_SMODE(HAS_SMODE)) u_system (
    .clk_i,.rst_ni,.external_irq_i,.i_axi_s(i_axi),.d_axi_s(d_axi),
    .debug_axi_s,.write_snoop_o(sram_write_snoop),.write_snoop_addr_o(sram_write_snoop_addr),
    .write_snoop_data_o(sram_write_snoop_data),.write_snoop_strb_o(sram_write_snoop_strb),
    .msip_o(msip),.mtip_o(mtip),.meip_o(meip),.seip_o(seip),.mtime_o(mtime),
    .host_boot_entry_o,.host_boot_flags_o,.host_event_valid_o,
    .host_event_ready_i,.host_event_kind_o,.host_event_data_o
  );
  assign soc_ready_o = rst_ni;
  assign irq_software_o = msip;
  assign irq_timer_o = mtip;
  assign irq_external_o = meip;
endmodule

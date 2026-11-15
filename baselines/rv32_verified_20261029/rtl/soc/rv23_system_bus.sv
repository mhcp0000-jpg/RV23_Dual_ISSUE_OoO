module rv23_system_bus #(
  parameter int unsigned CLOCK_HZ = 100_000_000,
  parameter int unsigned TIMEBASE_HZ = rv_soc_pkg::TIMEBASE_HZ,
  parameter int unsigned PLIC_NUM_SOURCES = rv_soc_pkg::PLIC_NUM_SOURCES,
  parameter string SRAM_INIT_FILE = "",
  parameter string BOOTROM_INIT_FILE = ""
) (
  input logic clk_i, rst_ni,
  input logic [PLIC_NUM_SOURCES-1:1] external_irq_i,
  rv_axi4_if.slave i_axi_s, d_axi_s, debug_axi_s,
  output logic write_snoop_o, msip_o, mtip_o, meip_o,
  output logic [31:0] write_snoop_addr_o,
  output logic [63:0] write_snoop_data_o,
  output logic [7:0] write_snoop_strb_o,
  output logic [63:0] mtime_o,
  output logic [31:0] host_boot_entry_o, host_boot_flags_o,
  output logic host_event_valid_o,
  input logic host_event_ready_i,
  output rv_soc_pkg::host_event_e host_event_kind_o,
  output logic [31:0] host_event_data_o
);
  import rv_soc_pkg::*;
  rv_axi4_if #(.ID_WIDTH(6)) sram_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(6)) clint_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(6)) plic_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(6)) host_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(6)) rom_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(6)) error_axi (.clk_i,.rst_ni);
  rv_local_mem_if sram_local (.clk_i,.rst_ni);
  rv_local_mem_if clint_local (.clk_i,.rst_ni);
  logic unused_seip;
  rv_axi_xbar u_main_xbar (
    .clk_i,.rst_ni,.m0_s(i_axi_s),.m1_s(d_axi_s),.m2_s(debug_axi_s),
    .s0_m(sram_axi),.s1_m(clint_axi),.s2_m(plic_axi),
    .s3_m(host_axi),.s4_m(rom_axi),.s5_m(error_axi)
  );
  rv_axi_to_local_bridge #(.AXI_ID_WIDTH(6),
    .TARGET_BASE_ADDR(rv23_pkg::SRAM_BASE),.TARGET_SIZE_KB(rv23_pkg::SRAM_KB),
    .TARGET_IS_DEVICE(0)) u_sram_bridge (
    .clk_i,.rst_ni,.axi_s(sram_axi),.local_bus(sram_local)
  );
  rv23_sram #(.INIT_FILE(SRAM_INIT_FILE)) u_sram (
    .clk_i,.rst_ni,.bus(sram_local),.write_snoop_o,.write_snoop_addr_o,
    .write_snoop_data_o,.write_snoop_strb_o
  );
  rv_axi_to_local_bridge #(.AXI_ID_WIDTH(6),
    .TARGET_BASE_ADDR(CLINT_BASE_ADDR),.TARGET_SIZE_KB(CLINT_SIZE_KB),
    .TARGET_IS_DEVICE(1)) u_clint_bridge (
    .clk_i,.rst_ni,.axi_s(clint_axi),.local_bus(clint_local)
  );
  rv_clint #(.CLOCK_HZ(CLOCK_HZ),.TIMEBASE_HZ(TIMEBASE_HZ)) u_clint (
    .clk_i,.rst_ni,.bus(clint_local),.msip_o,.mtip_o,.mtime_o
  );
  rv_plic #(.AXI_ID_WIDTH(6),.NUM_SOURCES(PLIC_NUM_SOURCES),.HAS_SMODE(0)) u_plic (
    .clk_i,.rst_ni,.axi_s(plic_axi),.source_i(external_irq_i),
    .meip_o,.seip_o(unused_seip)
  );
  rv_hostif #(.AXI_ID_WIDTH(6)) u_hostif (
    .clk_i,.rst_ni,.axi_s(host_axi),.boot_entry_o(host_boot_entry_o),
    .boot_flags_o(host_boot_flags_o),.event_valid_o(host_event_valid_o),
    .event_ready_i(host_event_ready_i),.event_kind_o(host_event_kind_o),
    .event_data_o(host_event_data_o)
  );
  rv_bootrom #(.AXI_ID_WIDTH(6),.INIT_FILE(BOOTROM_INIT_FILE)) u_bootrom (
    .clk_i,.rst_ni,.axi_s(rom_axi)
  );
  rv_axi_error_slave #(.ID_WIDTH(6)) u_error (.clk_i,.rst_ni,.axi_s(error_axi));
endmodule

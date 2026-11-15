// RV32IMFC_Zicsr_Zifencei SoC. The historical rv23 module prefix is retained.
module rv23_soc_top #(
  parameter int unsigned XLEN = 32,
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
  localparam int unsigned LOCAL_MEM_ID_WIDTH = 6;
  localparam int unsigned ROB_SEQ_WIDTH = rv_ooo_pkg::ROB_SEQ_WIDTH;
  localparam logic [XLEN-1:0] CORE_RESET_VECTOR = RESET_VECTOR;
  localparam logic [XLEN-1:0] BOOT_MTVEC_ADDR = TRAP_VECTOR;
  localparam bit HAS_C = 1, HAS_F = 1, HAS_SMODE = 0;
  localparam int IF_TARGET_BUFFER_ENTRIES = 16;
  localparam int BR_CHECKPOINTS = rv_ooo_pkg::CORE_CFG_BR_CHECKPOINTS;
  localparam bit AGU_LOAD_BYPASS = rv_ooo_pkg::CORE_CFG_AGU_LOAD_BYPASS;
  localparam bit EARLY_LOAD_SELECT = rv_ooo_pkg::CORE_CFG_EARLY_LOAD_SELECT;
  localparam bit COMPATIBLE_PAIR_SELECT = rv_ooo_pkg::CORE_CFG_COMPATIBLE_PAIR_SELECT;
  localparam bit BRANCH_TAG_PIPELINE = rv_ooo_pkg::CORE_CFG_BRANCH_TAG_PIPELINE;
  localparam bit DIV_TAG_PIPELINE = rv_ooo_pkg::CORE_CFG_DIV_TAG_PIPELINE;
  localparam bit INT_ISSUE_PIPELINE = rv_ooo_pkg::CORE_CFG_INT_ISSUE_PIPELINE;
  localparam int FPU_LATENCY = rv_ooo_pkg::CORE_CFG_FPU_LATENCY;
  logic                       imem_req_valid;
  logic                       imem_req_ready;
  logic [31:0]                imem_req_addr;
  logic [3:0]                 imem_req_id;
  logic [3:0]                 imem_req_epoch;
  logic                       imem_rsp_valid;
  logic                       imem_rsp_ready;
  logic [3:0]                 imem_rsp_id;
  logic [3:0]                 imem_rsp_epoch;
  logic [127:0]               imem_rsp_data;
  logic [1:0]                 imem_rsp_resp;

  logic [1:0]                 dmem_req_valid;
  logic [1:0]                 dmem_req_ready;
  logic [1:0][5:0]            dmem_req_id;
  logic [1:0]                 dmem_req_write;
  logic [1:0][31:0]           dmem_req_addr;
  logic [1:0][2:0]            dmem_req_size;
  logic [1:0][63:0]           dmem_req_wdata;
  logic [1:0][7:0]            dmem_req_wstrb;
  logic [1:0][1:0]            dmem_req_priv;
  logic [1:0][ROB_SEQ_WIDTH-1:0] dmem_req_rob_seq;
  logic [1:0]                 dmem_req_committed;
  logic [1:0]                 dmem_req_device;
  logic [1:0]                 dmem_rsp_valid;
  logic [1:0]                 dmem_rsp_ready;
  logic [1:0][5:0]            dmem_rsp_id;
  logic [1:0][63:0]           dmem_rsp_rdata;
  logic [1:0][1:0]            dmem_rsp_resp;
  logic [1:0][2:0]            dmem_rsp_replay;

  logic                       msip;
  logic                       mtip;
  logic                       meip;
  logic [63:0]                mtime;


  logic core_drained, fence_i, sram_write_snoop;
  logic [31:0] sram_write_snoop_addr;
  logic [63:0] sram_write_snoop_data;
  logic [7:0] sram_write_snoop_strb;
  wire core_rst_ni = rst_ni && core_run_i;
  logic i_idle, d_idle, arb_idle, if_quiescent;
  rv_local_mem_if lsu0_bus (.clk_i,.rst_ni);
  rv_local_mem_if lsu1_bus (.clk_i,.rst_ni);
  rv_local_mem_if i_cpu (.clk_i,.rst_ni);
  rv_local_mem_if i_cpu_hi (.clk_i,.rst_ni);
  rv_local_mem_if d_cpu (.clk_i,.rst_ni);
  rv_local_mem_if i_outbound (.clk_i,.rst_ni);
  rv_local_mem_if d_outbound (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) i_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) d_axi (.clk_i,.rst_ni);
  rv_ooo_core #(
    .XLEN           (XLEN),
    .PADDR_WIDTH    (32),
    .MEM_DATA_WIDTH (64),
    .HAS_C          (HAS_C),
    .HAS_F          (HAS_F),
    .HAS_SMODE      (HAS_SMODE),
    .FETCH_BYTES    (16),
    .IF_TARGET_BUFFER_ENTRIES(IF_TARGET_BUFFER_ENTRIES),
    .BR_CHECKPOINTS  (BR_CHECKPOINTS),
    .EARLY_LOAD_SELECT(EARLY_LOAD_SELECT), .AGU_LOAD_BYPASS(AGU_LOAD_BYPASS),
    .COMPATIBLE_PAIR_SELECT(COMPATIBLE_PAIR_SELECT),
    .BRANCH_TAG_PIPELINE(BRANCH_TAG_PIPELINE),
    .DIV_TAG_PIPELINE(DIV_TAG_PIPELINE),
    .INT_ISSUE_PIPELINE(INT_ISSUE_PIPELINE),
    .FPU_LATENCY(FPU_LATENCY),
    .RESET_VECTOR   (CORE_RESET_VECTOR),
    .TRAP_VECTOR    (XLEN'(BOOT_MTVEC_ADDR)),
    .ITIM_BASE_ADDR (rv23_pkg::SRAM_BASE),
    .ITIM_SIZE_KB   (rv23_pkg::SRAM_KB),
    .DTIM_BASE_ADDR (rv23_pkg::SRAM_BASE),
    .DTIM_SIZE_KB   (rv23_pkg::SRAM_KB)
  ) u_core (
    .clk_i,
    .rst_ni(core_rst_ni),
    .imem_req_valid_o (imem_req_valid),
    .imem_req_ready_i (imem_req_ready),
    .imem_req_addr_o  (imem_req_addr),
    .imem_req_id_o    (imem_req_id),
    .imem_req_epoch_o (imem_req_epoch),
    .imem_rsp_valid_i (imem_rsp_valid),
    .imem_rsp_ready_o (imem_rsp_ready),
    .imem_rsp_id_i    (imem_rsp_id),
    .imem_rsp_epoch_i (imem_rsp_epoch),
    .imem_rsp_data_i  (imem_rsp_data),
    .imem_rsp_resp_i  (imem_rsp_resp),
    .dmem_req_valid_o (dmem_req_valid),
    .dmem_req_ready_i (dmem_req_ready),
    .dmem_req_id_o    (dmem_req_id),
    .dmem_req_write_o (dmem_req_write),
    .dmem_req_addr_o  (dmem_req_addr),
    .dmem_req_size_o  (dmem_req_size),
    .dmem_req_wdata_o (dmem_req_wdata),
    .dmem_req_wstrb_o (dmem_req_wstrb),
    .dmem_req_priv_o  (dmem_req_priv),
    .dmem_req_rob_seq_o (dmem_req_rob_seq),
    .dmem_req_committed_o (dmem_req_committed),
    .dmem_req_device_o (dmem_req_device),
    .dmem_rsp_valid_i (dmem_rsp_valid),
    .dmem_rsp_ready_o (dmem_rsp_ready),
    .dmem_rsp_id_i    (dmem_rsp_id),
    .dmem_rsp_rdata_i (dmem_rsp_rdata),
    .dmem_rsp_resp_i  (dmem_rsp_resp),
    .dmem_rsp_replay_i(dmem_rsp_replay),
    .irq_software_i   (msip),
    .irq_timer_i      (mtip),
    .irq_external_i   (meip),
    .mtime_i          (mtime),
    .debug_halt_req_i (debug_halt_req_i),
    .debug_drained_o(core_drained),
    .fence_i_o(fence_i),
    .trace_valid_o,
    .trace_pc_o,
    .trace_instr_o,
    .trace_rd_o,
    .trace_rd_write_o,
    .trace_rd_fp_o,
    .trace_rd_wdata_o,
    .trace_trap_o,
    .trace_cause_o,
    .trace_tval_o
  );

  assign lsu0_bus.req_valid     = dmem_req_valid[0];
  assign lsu0_bus.req_id        = dmem_req_id[0];
  assign lsu0_bus.req_addr      = dmem_req_addr[0];
  assign lsu0_bus.req_write     = dmem_req_write[0];
  assign lsu0_bus.req_size      = dmem_req_size[0];
  assign lsu0_bus.req_wdata     = dmem_req_wdata[0];
  assign lsu0_bus.req_wstrb     = dmem_req_wstrb[0];
  assign lsu0_bus.req_priv      = rv_soc_pkg::privilege_e'(dmem_req_priv[0]);
  assign lsu0_bus.req_rob_seq   = dmem_req_rob_seq[0];
  assign lsu0_bus.req_committed = dmem_req_committed[0];
  assign lsu0_bus.req_device    = dmem_req_device[0];
  assign lsu0_bus.rsp_ready     = dmem_rsp_ready[0];
  assign dmem_req_ready[0]      = lsu0_bus.req_ready;
  assign dmem_rsp_valid[0]      = lsu0_bus.rsp_valid;
  assign dmem_rsp_id[0]         = lsu0_bus.rsp_id;
  assign dmem_rsp_rdata[0]      = lsu0_bus.rsp_rdata;
  assign dmem_rsp_resp[0]       = lsu0_bus.rsp_resp;
  assign dmem_rsp_replay[0]     = lsu0_bus.rsp_replay;

  assign lsu1_bus.req_valid     = dmem_req_valid[1];
  assign lsu1_bus.req_id        = dmem_req_id[1];
  assign lsu1_bus.req_addr      = dmem_req_addr[1];
  assign lsu1_bus.req_write     = dmem_req_write[1];
  assign lsu1_bus.req_size      = dmem_req_size[1];
  assign lsu1_bus.req_wdata     = dmem_req_wdata[1];
  assign lsu1_bus.req_wstrb     = dmem_req_wstrb[1];
  assign lsu1_bus.req_priv      = rv_soc_pkg::privilege_e'(dmem_req_priv[1]);
  assign lsu1_bus.req_rob_seq   = dmem_req_rob_seq[1];
  assign lsu1_bus.req_committed = dmem_req_committed[1];
  assign lsu1_bus.req_device    = dmem_req_device[1];
  assign lsu1_bus.rsp_ready     = dmem_rsp_ready[1];
  assign dmem_req_ready[1]      = lsu1_bus.req_ready;
  assign dmem_rsp_valid[1]      = lsu1_bus.rsp_valid;
  assign dmem_rsp_id[1]         = lsu1_bus.rsp_id;
  assign dmem_rsp_rdata[1]      = lsu1_bus.rsp_rdata;
  assign dmem_rsp_resp[1]       = lsu1_bus.rsp_resp;
  assign dmem_rsp_replay[1]     = lsu1_bus.rsp_replay;

  rv23_if_adapter u_if_adapter (
    .clk_i,.rst_ni,.halt_i(debug_halt_req_i),
    .req_valid_i(imem_req_valid),.req_ready_o(imem_req_ready),
    .req_addr_i(imem_req_addr),.req_id_i(imem_req_id),.req_epoch_i(imem_req_epoch),
    .rsp_valid_o(imem_rsp_valid),.rsp_ready_i(imem_rsp_ready),
    .rsp_id_o(imem_rsp_id),.rsp_epoch_o(imem_rsp_epoch),
    .rsp_data_o(imem_rsp_data),.rsp_resp_o(imem_rsp_resp),
    .quiescent_o(if_quiescent),.bus(i_cpu),.bus_hi(i_cpu_hi)
  );
  assign arb_idle=1'b1;
  rv23_cache #(.SIZE_KB(rv23_pkg::ICACHE_KB),.READ_ONLY(1)) u_icache (
    .clk_i,.rst_ni,.invalidate_i(fence_i),
    .snoop_valid_i(sram_write_snoop),.snoop_addr_i(sram_write_snoop_addr),
    .snoop_wdata_i(sram_write_snoop_data),.snoop_wstrb_i(sram_write_snoop_strb),
    .idle_o(i_idle),.cpu(i_cpu),.cpu_b(i_cpu_hi),.mem(i_outbound)
  );
  rv23_cache #(.SIZE_KB(rv23_pkg::DCACHE_KB)) u_dcache (
    .clk_i,.rst_ni,.invalidate_i(1'b0),
    .snoop_valid_i(sram_write_snoop),.snoop_addr_i(sram_write_snoop_addr),
    .snoop_wdata_i(sram_write_snoop_data),.snoop_wstrb_i(sram_write_snoop_strb),
    .idle_o(d_idle),.cpu(lsu0_bus),.cpu_b(lsu1_bus),.mem(d_outbound)
  );
  rv_local_to_axi_bridge #(.IS_INSTRUCTION(1)) u_i_bridge (
    .clk_i,.rst_ni,.local_bus(i_outbound),.axi_m(i_axi)
  );
  rv_local_to_axi_bridge u_d_bridge (
    .clk_i,.rst_ni,.local_bus(d_outbound),.axi_m(d_axi)
  );
  rv23_system_bus #(.CLOCK_HZ(CLOCK_HZ),.TIMEBASE_HZ(TIMEBASE_HZ),
    .PLIC_NUM_SOURCES(PLIC_NUM_SOURCES),.BOOTROM_INIT_FILE(BOOTROM_INIT_FILE),
    .SRAM_INIT_FILE(SRAM_INIT_FILE)) u_system (
    .clk_i,.rst_ni,.external_irq_i,.i_axi_s(i_axi),.d_axi_s(d_axi),
    .debug_axi_s,.write_snoop_o(sram_write_snoop),.write_snoop_addr_o(sram_write_snoop_addr),
    .write_snoop_data_o(sram_write_snoop_data),.write_snoop_strb_o(sram_write_snoop_strb),
    .msip_o(msip),.mtip_o(mtip),.meip_o(meip),.mtime_o(mtime),
    .host_boot_entry_o,.host_boot_flags_o,.host_event_valid_o,
    .host_event_ready_i,.host_event_kind_o,.host_event_data_o
  );
  assign soc_ready_o = rst_ni;
  assign irq_software_o = msip;
  assign irq_timer_o = mtip;
  assign irq_external_o = meip;
  assign debug_halted_o = rst_ni && core_drained && arb_idle &&
    i_idle && d_idle && if_quiescent;
endmodule

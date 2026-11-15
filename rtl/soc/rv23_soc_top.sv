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
  localparam int unsigned CORE_ADDR_WIDTH=HAS_MMU ? 64:32;
  localparam int unsigned LOCAL_MEM_ID_WIDTH = 6;
  localparam int unsigned ROB_SEQ_WIDTH = rv_ooo_pkg::ROB_SEQ_WIDTH;
  localparam logic [XLEN-1:0] CORE_RESET_VECTOR = RESET_VECTOR;
  localparam logic [XLEN-1:0] BOOT_MTVEC_ADDR = TRAP_VECTOR;
  localparam bit HAS_C = 1, HAS_F = 1;
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
  logic [CORE_ADDR_WIDTH-1:0] imem_req_addr;
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
  logic [1:0][CORE_ADDR_WIDTH-1:0] dmem_req_addr;
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
  logic seip;
  logic [63:0]                mtime;


  logic core_drained, fence_i, sram_write_snoop;
  logic imem_req_device;
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
  rv_local_mem_if ptw_bus (.clk_i,.rst_ni);
  rv_local_mem_if i_outbound (.clk_i,.rst_ni);
  rv_local_mem_if d_outbound (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) i_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) d_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) d_normal_axi (.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) atomic_axi (.clk_i,.rst_ni);
  logic atomic_reservation,atomic_valid,atomic_ready,atomic_word,atomic_privileged,atomic_clear;
  logic atomic_response_valid,atomic_response_ready,atomic_exception,atomic_idle;
  logic [31:0] atomic_address;
  logic [63:0] atomic_operand,atomic_data;
  logic [4:0] atomic_operation;
  logic [5:0] atomic_cause;
  rv23_atomic_engine u_atomic (
    .clk_i,.rst_ni(core_rst_ni),.request_valid_i(atomic_valid),.request_ready_o(atomic_ready),
    .request_address_i(atomic_address),.request_operand_i(atomic_operand),
    .request_operation_i(atomic_operation),.request_word_i(atomic_word),
    .request_privileged_i(atomic_privileged),.clear_reservation_i(atomic_clear),
    .write_snoop_i(sram_write_snoop),.write_snoop_address_i(sram_write_snoop_addr),
    .reservation_valid_o(atomic_reservation),.idle_o(atomic_idle),
    .response_valid_o(atomic_response_valid),.response_ready_i(atomic_response_ready),
    .response_data_o(atomic_data),.response_exception_o(atomic_exception),
    .response_cause_o(atomic_cause),.axi_m(atomic_axi));
  rv_local_mem_if cbo_bus(.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) cbo_axi(.clk_i,.rst_ni);
  rv_axi4_if #(.ID_WIDTH(4)) cache_cbo_axi(.clk_i,.rst_ni);
  logic cbo_cache_invalidate,cbo_cache_ready;
  logic [1:0] cbo_privilege;
  assign cbo_cache_ready=i_idle && d_idle && arb_idle && atomic_idle;
  logic cbo_memory_read,cbo_memory_device;
  assign cbo_bus.req_id=6'he;assign cbo_bus.req_write=!cbo_memory_read;
  assign cbo_bus.req_priv=rv_soc_pkg::privilege_e'(cbo_privilege);
  assign cbo_bus.req_rob_seq=0;assign cbo_bus.req_committed=1;assign cbo_bus.req_device=cbo_memory_device;
  rv_local_to_axi_bridge u_cbo_bridge(.clk_i,.rst_ni,.local_bus(cbo_bus),.axi_m(cbo_axi));
  rv23_axi_mux u_cache_cbo_mux(.clk_i,.rst_ni,.a_s(d_normal_axi),.b_s(cbo_axi),.out_m(cache_cbo_axi));
  rv23_axi_mux u_data_mux(.clk_i,.rst_ni,.a_s(cache_cbo_axi),.b_s(atomic_axi),.out_m(d_axi));
  rv_ooo_core #(
    .XLEN           (XLEN),
    .PADDR_WIDTH    (CORE_ADDR_WIDTH),
    .MEM_DATA_WIDTH (64),
    .HAS_C          (HAS_C),
    .HAS_F          (HAS_F),
    .HAS_SMODE      (HAS_SMODE),
    .HAS_V(HAS_V),.HAS_H(HAS_H),.HAS_ZAWRS(HAS_ZAWRS),.HAS_ZIMOP(HAS_ZIMOP),.HAS_ZCMOP(HAS_ZCMOP),.HAS_ZCB(HAS_ZCB),.HAS_SVINVAL(HAS_SVINVAL),.HAS_SSNPM(HAS_SSNPM),.HAS_D(HAS_D),.HAS_ZFHMIN(HAS_ZFHMIN),.HAS_ZFA(HAS_ZFA),.HAS_MISALIGNED(HAS_MISALIGNED),.HAS_CBO(HAS_CBO),.HAS_A(HAS_A), .HAS_B(HAS_B), .HAS_ZICOND(HAS_ZICOND), .HAS_MMU(HAS_MMU),
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
    .cbo_memory_read_o(cbo_memory_read),.cbo_memory_device_o(cbo_memory_device),.cbo_memory_size_o(cbo_bus.req_size),
    .cbo_memory_data_o(cbo_bus.req_wdata),.cbo_memory_strobe_o(cbo_bus.req_wstrb),
    .cbo_memory_response_data_i(cbo_bus.rsp_rdata),
    .cbo_write_valid_o(cbo_bus.req_valid),.cbo_write_ready_i(cbo_bus.req_ready),
    .cbo_write_address_o(cbo_bus.req_addr),.cbo_write_privilege_o(cbo_privilege),
    .cbo_write_response_valid_i(cbo_bus.rsp_valid),.cbo_write_response_ready_o(cbo_bus.rsp_ready),
    .cbo_write_response_error_i(cbo_bus.rsp_resp[1] || cbo_bus.rsp_replay!=rv_soc_pkg::MEM_REPLAY_NONE),
    .cbo_cache_invalidate_o(cbo_cache_invalidate),.cbo_cache_invalidate_ready_i(cbo_cache_ready),
    .atomic_reservation_i(atomic_reservation),.atomic_valid_o(atomic_valid),.atomic_ready_i(atomic_ready),.atomic_address_o(atomic_address),
    .atomic_operand_o(atomic_operand),.atomic_operation_o(atomic_operation),
    .atomic_word_o(atomic_word),.atomic_privileged_o(atomic_privileged),.atomic_clear_o(atomic_clear),
    .atomic_response_valid_i(atomic_response_valid),.atomic_response_ready_o(atomic_response_ready),
    .atomic_data_i(atomic_data),.atomic_exception_i(atomic_exception),.atomic_cause_i(atomic_cause),
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
    .irq_supervisor_external_i(seip),
    .imem_req_device_o(imem_req_device),
    .ptw_req_valid_o(ptw_bus.req_valid),.ptw_req_ready_i(ptw_bus.req_ready),.ptw_req_address_o(ptw_bus.req_addr),
    .ptw_req_device_o(ptw_bus.req_device),.ptw_rsp_valid_i(ptw_bus.rsp_valid),.ptw_rsp_ready_o(ptw_bus.rsp_ready),
    .ptw_rsp_data_i(ptw_bus.rsp_rdata),.ptw_rsp_error_i(ptw_bus.rsp_resp!=rv_soc_pkg::AXI_RESP_OKAY ||
      ptw_bus.rsp_replay!=rv_soc_pkg::MEM_REPLAY_NONE),
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
  assign lsu0_bus.req_addr      = 32'(dmem_req_addr[0]);
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
  assign lsu1_bus.req_addr      = 32'(dmem_req_addr[1]);
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
    .clk_i,.rst_ni,.halt_i(HAS_MMU ? 1'b0:debug_halt_req_i),
    .req_valid_i(imem_req_valid),.req_ready_o(imem_req_ready),
    .req_addr_i(32'(imem_req_addr)),.req_device_i(imem_req_device),.req_id_i(imem_req_id),.req_epoch_i(imem_req_epoch),
    .rsp_valid_o(imem_rsp_valid),.rsp_ready_i(imem_rsp_ready),
    .rsp_id_o(imem_rsp_id),.rsp_epoch_o(imem_rsp_epoch),
    .rsp_data_o(imem_rsp_data),.rsp_resp_o(imem_rsp_resp),
    .quiescent_o(if_quiescent),.bus(i_cpu),.bus_hi(i_cpu_hi)
  );
  assign ptw_bus.req_id=0;assign ptw_bus.req_write=0;assign ptw_bus.req_size=3;
  assign ptw_bus.req_wdata=0;assign ptw_bus.req_wstrb=0;assign ptw_bus.req_priv=rv_soc_pkg::PRIV_S;
  assign ptw_bus.req_rob_seq=0;assign ptw_bus.req_committed=0;
  if(HAS_MMU) begin:g_ptw_port
    rv23_lsu_arbiter u_share (.clk_i,.rst_ni,.idle_o(arb_idle),.a(lsu1_bus),.b(ptw_bus),.out_bus(d_cpu));
  end else begin:g_direct_port
    assign arb_idle=1;
    assign ptw_bus.req_ready=0;assign ptw_bus.rsp_valid=0;assign ptw_bus.rsp_id=0;
    assign ptw_bus.rsp_rdata=0;assign ptw_bus.rsp_resp=rv_soc_pkg::AXI_RESP_OKAY;
    assign ptw_bus.rsp_replay=rv_soc_pkg::MEM_REPLAY_NONE;
    assign d_cpu.req_valid=lsu1_bus.req_valid;
    assign d_cpu.req_id=lsu1_bus.req_id;
    assign d_cpu.req_addr=lsu1_bus.req_addr;
    assign d_cpu.req_write=lsu1_bus.req_write;
    assign d_cpu.req_size=lsu1_bus.req_size;
    assign d_cpu.req_wdata=lsu1_bus.req_wdata;
    assign d_cpu.req_wstrb=lsu1_bus.req_wstrb;
    assign d_cpu.req_priv=lsu1_bus.req_priv;
    assign d_cpu.req_rob_seq=lsu1_bus.req_rob_seq;
    assign d_cpu.req_committed=lsu1_bus.req_committed;
    assign d_cpu.req_device=lsu1_bus.req_device;
    assign lsu1_bus.req_ready=d_cpu.req_ready;
    assign lsu1_bus.rsp_valid=d_cpu.rsp_valid;
    assign lsu1_bus.rsp_id=d_cpu.rsp_id;
    assign lsu1_bus.rsp_rdata=d_cpu.rsp_rdata;
    assign lsu1_bus.rsp_resp=d_cpu.rsp_resp;
    assign lsu1_bus.rsp_replay=d_cpu.rsp_replay;
    assign d_cpu.rsp_ready=lsu1_bus.rsp_ready;
  end
  rv23_cache #(.SIZE_KB(rv23_pkg::ICACHE_KB),.READ_ONLY(1)) u_icache (
    .clk_i,.rst_ni,.invalidate_i(fence_i || (cbo_cache_invalidate && cbo_cache_ready)),
    .snoop_valid_i(sram_write_snoop),.snoop_addr_i(sram_write_snoop_addr),
    .snoop_wdata_i(sram_write_snoop_data),.snoop_wstrb_i(sram_write_snoop_strb),
    .idle_o(i_idle),.cpu(i_cpu),.cpu_b(i_cpu_hi),.mem(i_outbound)
  );
  rv23_cache #(.SIZE_KB(rv23_pkg::DCACHE_KB)) u_dcache (
    .clk_i,.rst_ni,.invalidate_i(cbo_cache_invalidate && cbo_cache_ready),
    .snoop_valid_i(sram_write_snoop),.snoop_addr_i(sram_write_snoop_addr),
    .snoop_wdata_i(sram_write_snoop_data),.snoop_wstrb_i(sram_write_snoop_strb),
    .idle_o(d_idle),.cpu(lsu0_bus),.cpu_b(d_cpu),.mem(d_outbound)
  );
  rv_local_to_axi_bridge #(.IS_INSTRUCTION(1)) u_i_bridge (
    .clk_i,.rst_ni,.local_bus(i_outbound),.axi_m(i_axi)
  );
  rv_local_to_axi_bridge u_d_bridge (
    .clk_i,.rst_ni,.local_bus(d_outbound),.axi_m(d_normal_axi)
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
  assign debug_halted_o = rst_ni && core_drained && arb_idle &&
    i_idle && d_idle && if_quiescent;
endmodule

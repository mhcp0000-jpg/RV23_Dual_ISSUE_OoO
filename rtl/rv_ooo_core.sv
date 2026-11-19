module rv_ooo_core #(
  parameter bit HAS_A=0,
  parameter bit HAS_V=0,
  parameter bit HAS_H=0,
  parameter bit HAS_CBO=0,
  parameter bit HAS_MISALIGNED=0,
  parameter bit HAS_D=0,HAS_ZFHMIN=0,HAS_ZFA=0,
  parameter bit HAS_SSNPM=0,
  parameter bit HAS_ZAWRS=0,HAS_ZIMOP=0,HAS_ZCMOP=0,HAS_ZCB=0,HAS_SVINVAL=0,
  parameter bit AGU_LOAD_BYPASS = rv_ooo_pkg::CORE_CFG_AGU_LOAD_BYPASS,
  parameter bit EARLY_LOAD_SELECT = rv_ooo_pkg::CORE_CFG_EARLY_LOAD_SELECT,
  parameter bit COMPATIBLE_PAIR_SELECT = rv_ooo_pkg::CORE_CFG_COMPATIBLE_PAIR_SELECT,
  parameter bit BRANCH_TAG_PIPELINE = rv_ooo_pkg::CORE_CFG_BRANCH_TAG_PIPELINE,
  parameter bit DIV_TAG_PIPELINE = rv_ooo_pkg::CORE_CFG_DIV_TAG_PIPELINE,
  parameter bit INT_ISSUE_PIPELINE = rv_ooo_pkg::CORE_CFG_INT_ISSUE_PIPELINE,
  parameter bit SYSTEM_RESULT_PIPELINE = rv_ooo_pkg::CORE_CFG_SYSTEM_RESULT_PIPELINE,
  parameter bit ROB_COMPLETION_PIPELINE = rv_ooo_pkg::CORE_CFG_ROB_COMPLETION_PIPELINE,
  parameter bit LSU_VALIDATION_PIPELINE = rv_ooo_pkg::CORE_CFG_LSU_VALIDATION_PIPELINE,
  parameter bit AGU_EA_PRECOMPUTE = rv_ooo_pkg::CORE_CFG_AGU_EA_PRECOMPUTE,
  parameter int unsigned FPU_LATENCY = rv_ooo_pkg::CORE_CFG_FPU_LATENCY,
  parameter int unsigned XLEN             = 32,
  parameter int unsigned PADDR_WIDTH      = 32,
  parameter int unsigned MEM_DATA_WIDTH   = 64,
  parameter bit          HAS_C            = 1'b1,
  parameter bit          HAS_F            = 1'b1,
  parameter bit          HAS_SMODE        = 1'b0,
  parameter bit          HAS_B            = 1'b0,
  parameter bit          HAS_ZICOND       = 1'b0,
  parameter bit HAS_MMU=0,
  parameter int unsigned FETCH_BYTES      = 16,
  parameter int unsigned IF_TARGET_BUFFER_ENTRIES = 16,
  parameter int unsigned ROB_ENTRIES      = 48,
  parameter int unsigned ROB_SEQ_WIDTH    = rv_ooo_pkg::ROB_SEQ_WIDTH,
  parameter int unsigned INT_PHYS_REGS    = 80,
  parameter int unsigned FP_PHYS_REGS     = 80,
  parameter int unsigned INT_IQ_ENTRIES   = 24,
  parameter int unsigned MEM_IQ_ENTRIES   = 16,
  parameter int unsigned FP_IQ_ENTRIES    = 16,
  parameter int unsigned LQ_ENTRIES       = 24,
  parameter int unsigned SQ_ENTRIES       = 16,
  parameter int unsigned STORE_BUFFER_ENTRIES = 16,
  parameter int unsigned BR_CHECKPOINTS   = rv_ooo_pkg::CORE_CFG_BR_CHECKPOINTS,
  parameter logic [XLEN-1:0] RESET_VECTOR = 'h8000_0000,
  parameter logic [XLEN-1:0] TRAP_VECTOR  = 'h8000_0000,
  parameter logic [PADDR_WIDTH-1:0] ITIM_BASE_ADDR = 'h8000_0000,
  parameter int unsigned ITIM_SIZE_KB     = 128,
  parameter logic [PADDR_WIDTH-1:0] DTIM_BASE_ADDR = 'h8002_0000,
  parameter int unsigned DTIM_SIZE_KB     = 128
) (
  output logic cbo_memory_read_o,
  output logic cbo_memory_device_o,
  output logic cbo_memory_use_dcache_o,
  output logic [2:0] cbo_memory_size_o,
  output logic [63:0] cbo_memory_data_o,
  output logic [7:0] cbo_memory_strobe_o,
  input logic [63:0] cbo_memory_response_data_i=0,
  output logic cbo_write_valid_o,
  input logic cbo_write_ready_i=0,
  output logic [31:0] cbo_write_address_o,
  output logic [1:0] cbo_write_privilege_o,
  input logic cbo_write_response_valid_i=0,cbo_write_response_error_i=0,
  output logic cbo_write_response_ready_o,cbo_cache_invalidate_o,
  input logic cbo_cache_invalidate_ready_i=0,
  output logic atomic_valid_o,
  input logic atomic_ready_i=0,
  input logic atomic_reservation_i=0,
  output logic [31:0] atomic_address_o,
  output logic [63:0] atomic_operand_o,
  output logic [4:0] atomic_operation_o,
  output logic atomic_word_o,atomic_privileged_o,atomic_clear_o,
  input logic atomic_response_valid_i=0,
  output logic atomic_response_ready_o,
  input logic [63:0] atomic_data_i=0,
  input logic atomic_exception_i=0,
  input logic [5:0] atomic_cause_i=0,
  input  logic                         clk_i,
  input  logic                         rst_ni,

  output logic                         imem_req_valid_o,
  input  logic                         imem_req_ready_i,
  output logic [PADDR_WIDTH-1:0]       imem_req_addr_o,
  output logic [3:0]                   imem_req_id_o,
  output logic [3:0]                   imem_req_epoch_o,
  input  logic                         imem_rsp_valid_i,
  output logic                         imem_rsp_ready_o,
  input  logic [3:0]                   imem_rsp_id_i,
  input  logic [3:0]                   imem_rsp_epoch_i,
  input  logic [FETCH_BYTES*8-1:0]     imem_rsp_data_i,
  input  logic [1:0]                   imem_rsp_resp_i,

  output logic [1:0]                   dmem_req_valid_o,
  input  logic [1:0]                   dmem_req_ready_i,
  output logic [1:0][5:0]              dmem_req_id_o,
  output logic [1:0]                   dmem_req_write_o,
  output logic [1:0][PADDR_WIDTH-1:0]  dmem_req_addr_o,
  output logic [1:0][2:0]              dmem_req_size_o,
  output logic [1:0][MEM_DATA_WIDTH-1:0] dmem_req_wdata_o,
  output logic [1:0][MEM_DATA_WIDTH/8-1:0] dmem_req_wstrb_o,
  output logic [1:0][1:0]              dmem_req_priv_o,
  output logic [1:0][ROB_SEQ_WIDTH-1:0] dmem_req_rob_seq_o,
  output logic [1:0]                   dmem_req_committed_o,
  output logic [1:0]                   dmem_req_device_o,
  input  logic [1:0]                   dmem_rsp_valid_i,
  output logic [1:0]                   dmem_rsp_ready_o,
  input  logic [1:0][5:0]              dmem_rsp_id_i,
  input  logic [1:0][MEM_DATA_WIDTH-1:0] dmem_rsp_rdata_i,
  input  logic [1:0][1:0]              dmem_rsp_resp_i,
  input  logic [1:0][2:0]              dmem_rsp_replay_i,

  input  logic                         irq_software_i,
  input  logic                         irq_timer_i,
  input  logic                         irq_external_i,
  input logic irq_supervisor_external_i=1'b0,
  output logic [1:0] privilege_o,
  output logic [XLEN-1:0] mstatus_o,
  output logic [63:0] satp_o,menvcfg_o,senvcfg_o,
  output logic ptw_req_valid_o,ptw_req_device_o,
  input logic ptw_req_ready_i=0,
  output logic [31:0] ptw_req_address_o,
  input logic ptw_rsp_valid_i=0,ptw_rsp_error_i=0,
  output logic ptw_rsp_ready_o,
  input logic [63:0] ptw_rsp_data_i=0,
  output logic imem_req_device_o,
  input  logic [63:0]                  mtime_i,
  input  logic                         debug_halt_req_i,
  output logic                         debug_drained_o,
  output logic                         fence_i_o,

  output logic [1:0]                   trace_valid_o,
  output logic [1:0][XLEN-1:0]         trace_pc_o,
  output logic [1:0][31:0]             trace_instr_o,
  output logic [1:0][4:0]              trace_rd_o,
  output logic [1:0]                   trace_rd_write_o,
  output logic [1:0]                   trace_rd_fp_o,
  output logic [1:0][XLEN-1:0]         trace_rd_wdata_o,
  output logic [1:0]                   trace_trap_o,
  output logic [1:0][5:0]              trace_cause_o,
  output logic [1:0][XLEN-1:0]         trace_tval_o
);

  import rv_ooo_pkg::*;
  assign fence_i_o = (trace_valid_o[0] && !trace_trap_o[0] &&
    (trace_instr_o[0] & 32'h0000_707f) == 32'h0000_100f) ||
    (trace_valid_o[1] && !trace_trap_o[1] &&
    (trace_instr_o[1] & 32'h0000_707f) == 32'h0000_100f);


  localparam int unsigned IFU_PMP_PORTS = FETCH_BYTES/2;

  logic [1:0]                    fe_valid;
  logic [1:0]                    fe_ready;
  logic [1:0][XLEN-1:0]          fe_pc;
  logic [1:0][31:0]              fe_instr;
  inst_len_e [1:0]               fe_inst_len;
  prediction_meta_t [1:0]        fe_prediction;
  logic [1:0]                    fe_fetch_fault;
  logic [1:0][5:0] fe_fetch_fault_cause;
  logic [1:0][XLEN-1:0] fe_fetch_fault_address;
  logic [1:0][63:0] fe_fetch_guest_address;
  logic [1:0] fe_fetch_implicit_guest_access;
  logic [63:0] fe_imem_guest_address;
  logic fe_imem_implicit_guest_access;
  logic [5:0] fe_imem_rsp_fault_cause;
  logic [IFU_PMP_PORTS-1:0][PADDR_WIDTH-1:0] ifu_physical_pmp_address;
  logic [4:0] ptw_valid,ptw_device,ptw_ready,ptw_rsp_valid,ptw_rsp_ready,ptw_error;
  logic [4:0][55:0] ptw_address;
  logic [4:0][63:0] ptw_data;
  logic translation_invalidate,if_translation_idle,ptw_idle,backend_debug_drained;

  logic                          redirect_valid;
  logic [XLEN-1:0]               redirect_pc;
  logic                          bp_resolve_valid;
  logic [XLEN-1:0]               bp_resolve_pc, bp_resolve_target;
  logic [31:0]                   bp_resolve_instruction;
  inst_len_e                     bp_resolve_inst_len;
  logic                          bp_resolve_taken, bp_resolve_mispredict;
  prediction_meta_t              bp_resolve_prediction;
  logic [1:0]                    bp_commit_valid, bp_commit_taken;
  logic [1:0][XLEN-1:0]          bp_commit_pc;
  logic [1:0][31:0]              bp_commit_instruction;
  inst_len_e [1:0]               bp_commit_inst_len;
  privilege_e                    current_privilege;
  logic current_virtual;
  logic [63:0] hstatus,vsstatus,vsatp,hgatp,henvcfg;
  assign privilege_o=current_privilege;
  logic [7:0][7:0]               pmpcfg;
  logic [7:0][PADDR_WIDTH-3:0]   pmpaddr;

  logic                          fe_imem_req_valid, fe_imem_req_ready;
  logic [PADDR_WIDTH-1:0]        fe_imem_req_addr;
  logic [3:0]                    fe_imem_req_id, fe_imem_req_epoch;
  logic                          fe_imem_rsp_valid, fe_imem_rsp_ready;
  logic [3:0]                    fe_imem_rsp_id, fe_imem_rsp_epoch;
  logic [FETCH_BYTES*8-1:0]      fe_imem_rsp_data;
  logic [1:0]                    fe_imem_rsp_resp;
  logic [IFU_PMP_PORTS-1:0]      ifu_pmp_check_valid;
  logic [IFU_PMP_PORTS-1:0][PADDR_WIDTH-1:0]
                                  ifu_pmp_check_address;
  logic [IFU_PMP_PORTS-1:0][2:0] ifu_pmp_check_size;
  logic [IFU_PMP_PORTS-1:0][2:0] ifu_pmp_check_access;
  logic [IFU_PMP_PORTS-1:0]      ifu_pmp_allow, ifu_pmp_matched;
  logic [IFU_PMP_PORTS-1:0][PADDR_WIDTH-1:0]
                                  ifu_pmp_fault_address;
  privilege_e [IFU_PMP_PORTS-1:0] ifu_pmp_privilege;

  assign translation_invalidate=fence_i_o || (trace_valid_o[0] && !trace_trap_o[0] &&
    (((trace_instr_o[0] & 32'hfe007fff)==32'h12000073) ||
     (HAS_SVINVAL && ((trace_instr_o[0] & 32'hfe007fff)==32'h16000073 ||
       trace_instr_o[0]==32'h18000073 || trace_instr_o[0]==32'h18100073)) ||
     (HAS_H && rv_hypervisor_decode_pkg::is_hypervisor_fence(trace_instr_o[0],XLEN,HAS_SVINVAL)) ||
     (trace_instr_o[0][6:0]==7'h73 && trace_instr_o[0][13:12]!=0 &&
      ((trace_instr_o[0][31:20]==12'h180) || (trace_instr_o[0][31:20]==12'h100) ||
       (trace_instr_o[0][31:20]==12'h300) || (trace_instr_o[0][31:20]==12'h30a) ||
       (trace_instr_o[0][31:20]>=12'h3a0 && trace_instr_o[0][31:20]<=12'h3bf) ||
       (HAS_H && (trace_instr_o[0][31:28]==4'h2 || trace_instr_o[0][31:28]==4'h6))))));
  assign debug_drained_o=backend_debug_drained && if_translation_idle && ptw_idle;

  // The backend may choose a different LSU source while a downstream port is
  // backpressured (for example, when a committed store gains priority over a
  // load).  One fall-through entry per physical LSU port decouples that
  // arbitration from the external ready/valid contract.  Acceptance into this
  // buffer is also the LSQ's issue point, so a later flush can retain a killed
  // outstanding load until its response is drained without reusing its ID.
  logic [1:0]                    backend_dmem_req_valid;
  logic [1:0]                    backend_dmem_req_ready;
  logic [1:0][5:0]               backend_dmem_req_id;
  logic [1:0]                    backend_dmem_req_write;
  logic [1:0][PADDR_WIDTH-1:0]   backend_dmem_req_addr;
  logic [1:0][2:0]               backend_dmem_req_size;
  logic [1:0][MEM_DATA_WIDTH-1:0] backend_dmem_req_wdata;
  logic [1:0][MEM_DATA_WIDTH/8-1:0] backend_dmem_req_wstrb;
  logic [1:0][1:0]               backend_dmem_req_priv;
  logic [1:0][ROB_SEQ_WIDTH-1:0] backend_dmem_req_rob_seq;
  logic [1:0]                    backend_dmem_req_committed;
  logic [1:0]                    backend_dmem_req_device;

  logic [1:0]                    dmem_hold_valid_q;
  logic [1:0][5:0]               dmem_hold_id_q;
  logic [1:0]                    dmem_hold_write_q;
  logic [1:0][PADDR_WIDTH-1:0]   dmem_hold_addr_q;
  logic [1:0][2:0]               dmem_hold_size_q;
  logic [1:0][MEM_DATA_WIDTH-1:0] dmem_hold_wdata_q;
  logic [1:0][MEM_DATA_WIDTH/8-1:0] dmem_hold_wstrb_q;
  logic [1:0][1:0]               dmem_hold_priv_q;
  logic [1:0][ROB_SEQ_WIDTH-1:0] dmem_hold_rob_seq_q;
  logic [1:0]                    dmem_hold_committed_q;
  logic [1:0]                    dmem_hold_device_q;

  initial begin : p_parameter_checks
    if (!is_supported_xlen(XLEN))
      $fatal(1, "XLEN must be 32 or 64");
    if ((FETCH_BYTES < 8) || ((FETCH_BYTES & (FETCH_BYTES-1)) != 0))
      $fatal(1, "FETCH_BYTES must be a power of two and at least 8");
    if ((IF_TARGET_BUFFER_ENTRIES < 2) ||
        ((IF_TARGET_BUFFER_ENTRIES & (IF_TARGET_BUFFER_ENTRIES-1)) != 0))
      $fatal(1, "IF_TARGET_BUFFER_ENTRIES must be a power of two");
    if (PADDR_WIDTH == 0)
      $fatal(1, "PADDR_WIDTH must be greater than zero");
    if ((MEM_DATA_WIDTH < XLEN) || ((MEM_DATA_WIDTH % 8) != 0))
      $fatal(1, "MEM_DATA_WIDTH must cover XLEN and contain whole bytes");
    if (ROB_ENTRIES < 8)
      $fatal(1, "ROB_ENTRIES is too small for the baseline pipeline");
    if (ROB_ENTRIES >= (1 << (ROB_SEQ_WIDTH-1)))
      $fatal(1, "ROB_ENTRIES must be less than half the ROB sequence space");
    if (INT_PHYS_REGS < ARCH_INT_REGS)
      $fatal(1, "INT_PHYS_REGS must cover all architectural registers");
    if (FP_PHYS_REGS < ARCH_FP_REGS)
      $fatal(1, "FP_PHYS_REGS must cover all architectural registers");
    if ((INT_IQ_ENTRIES == 0) || (MEM_IQ_ENTRIES == 0) || (FP_IQ_ENTRIES == 0))
      $fatal(1, "Issue queues must contain at least one entry");
    if ((LQ_ENTRIES == 0) || (SQ_ENTRIES == 0) ||
        (STORE_BUFFER_ENTRIES == 0) || (BR_CHECKPOINTS == 0))
      $fatal(1, "LQ, SQ, store buffer, and branch checkpoints cannot be empty");
  end

  rv_frontend #(
    .XLEN         (XLEN),
    .PADDR_WIDTH  (PADDR_WIDTH),
    .FETCH_BYTES  (FETCH_BYTES),
    .TARGET_BUFFER_ENTRIES(IF_TARGET_BUFFER_ENTRIES), .ENABLE_TARGET_BUFFER(!HAS_MMU),
    .RESET_VECTOR (RESET_VECTOR)
  ) u_frontend (
    .clk_i,
    .rst_ni,
    .redirect_valid_i     (redirect_valid),
    .redirect_pc_i        (redirect_pc),
    .predictor_resolve_valid_i(bp_resolve_valid),
    .predictor_resolve_pc_i(bp_resolve_pc),
    .predictor_resolve_instruction_i(bp_resolve_instruction),
    .predictor_resolve_inst_len_i(bp_resolve_inst_len),
    .predictor_resolve_taken_i(bp_resolve_taken),
    .predictor_resolve_target_i(bp_resolve_target),
    .predictor_resolve_mispredict_i(bp_resolve_mispredict),
    .predictor_resolve_prediction_i(bp_resolve_prediction),
    .predictor_commit_valid_i(bp_commit_valid),
    .predictor_commit_pc_i(bp_commit_pc),
    .predictor_commit_instruction_i(bp_commit_instruction),
    .predictor_commit_inst_len_i(bp_commit_inst_len),
    .predictor_commit_taken_i(bp_commit_taken),
    .fetch_valid_o        (fe_valid),
    .fetch_ready_i        (fe_ready),
    .fetch_pc_o           (fe_pc),
    .fetch_instr_o        (fe_instr),
    .fetch_inst_len_o     (fe_inst_len),
    .fetch_prediction_o   (fe_prediction),
    .fetch_fault_o        (fe_fetch_fault),
    .fetch_fault_cause_o(fe_fetch_fault_cause),.fetch_fault_address_o(fe_fetch_fault_address),
    .fetch_guest_address_o(fe_fetch_guest_address),.fetch_implicit_guest_access_o(fe_fetch_implicit_guest_access),
    .imem_req_valid_o    (fe_imem_req_valid),
    .imem_req_ready_i    (fe_imem_req_ready),
    .imem_req_addr_o     (fe_imem_req_addr),
    .imem_req_id_o       (fe_imem_req_id),
    .imem_req_epoch_o    (fe_imem_req_epoch),
    .pmp_check_valid_o   (ifu_pmp_check_valid),
    .pmp_check_address_o (ifu_pmp_check_address),
    .pmp_check_allow_i   (ifu_pmp_allow),
    .imem_rsp_valid_i    (fe_imem_rsp_valid),
    .imem_rsp_ready_o    (fe_imem_rsp_ready),
    .imem_rsp_id_i       (fe_imem_rsp_id),
    .imem_rsp_epoch_i    (fe_imem_rsp_epoch),
    .imem_rsp_data_i     (fe_imem_rsp_data),
    .imem_rsp_resp_i     (fe_imem_rsp_resp),.imem_rsp_fault_cause_i(fe_imem_rsp_fault_cause),
    .imem_rsp_guest_address_i(fe_imem_guest_address),.imem_rsp_implicit_guest_access_i(fe_imem_implicit_guest_access)
  );

  for (genvar parcel = 0; parcel < IFU_PMP_PORTS; parcel++) begin : g_ifu_pmp
    assign ifu_pmp_check_size[parcel] = 3'd1; // 2-byte parcel
    assign ifu_pmp_check_access[parcel] = 3'b100;
    assign ifu_pmp_privilege[parcel] = current_privilege;
  end
  rv_pmp #(
    .PADDR_WIDTH(PADDR_WIDTH), .PMP_ENTRIES(8),
    .CHECK_PORTS(IFU_PMP_PORTS)
  ) u_ifu_pmp (
    .pmpcfg_i(pmpcfg), .pmpaddr_i(pmpaddr),
    .check_valid_i(ifu_pmp_check_valid),
    .check_address_i(ifu_physical_pmp_address),
    .check_size_i(ifu_pmp_check_size),
    .check_access_i(ifu_pmp_check_access),
    .check_privilege_i(ifu_pmp_privilege), .allow_o(ifu_pmp_allow),
    .matched_o(ifu_pmp_matched), .fault_address_o(ifu_pmp_fault_address)
  );

  if(HAS_MMU) begin:g_mmu
    logic [31:0] if_physical,if_bus_address;
    rv23_if_translate #(.PADDR_WIDTH(32),.FETCH_BYTES(FETCH_BYTES)) u_if (
      // Trap/return and committed translation CSR state changes take effect
      // on this edge. The redirect target must be accepted on a later edge,
      // after privilege/V/satp/PMP authority has changed. Otherwise a trap
      // handler fetch can inherit the faulting guest's translation context.
      .clk_i,.rst_ni,.invalidate_i(translation_invalidate),
      .halt_i(debug_halt_req_i || redirect_valid || translation_invalidate),
      .req_valid_i(fe_imem_req_valid),.req_ready_o(fe_imem_req_ready),.req_address_i(64'(fe_imem_req_addr)),
      .req_id_i(fe_imem_req_id),.req_epoch_i(fe_imem_req_epoch),.privilege_i(current_privilege),
      .virtual_i(current_virtual),.mxr_i(current_virtual?vsstatus[19]:mstatus_o[19]),.hs_mxr_i(mstatus_o[19]),.pbmt_enable_i(menvcfg_o[62]),
      .guest_pbmt_enable_i(henvcfg[62]),.satp_i(satp_o),.vsatp_i(vsatp),.hgatp_i(hgatp),
      .rsp_valid_o(fe_imem_rsp_valid),.rsp_ready_i(fe_imem_rsp_ready),.rsp_id_o(fe_imem_rsp_id),
      .rsp_epoch_o(fe_imem_rsp_epoch),.rsp_data_o(fe_imem_rsp_data),.rsp_resp_o(fe_imem_rsp_resp),
        .rsp_cause_o(fe_imem_rsp_fault_cause),.rsp_guest_address_o(fe_imem_guest_address),.rsp_implicit_guest_access_o(fe_imem_implicit_guest_access),
      .physical_address_o(if_physical),.idle_o(if_translation_idle),
      .bus_valid_o(imem_req_valid_o),.bus_ready_i(imem_req_ready_i),.bus_address_o(if_bus_address),
      .bus_id_o(imem_req_id_o),.bus_epoch_o(imem_req_epoch_o),.bus_device_o(imem_req_device_o),
      .bus_rsp_valid_i(imem_rsp_valid_i),.bus_rsp_ready_o(imem_rsp_ready_o),
      .bus_rsp_id_i(imem_rsp_id_i),.bus_rsp_epoch_i(imem_rsp_epoch_i),
      .bus_rsp_data_i(imem_rsp_data_i),.bus_rsp_resp_i(imem_rsp_resp_i),
      .mem_valid_o(ptw_valid[0]),.mem_device_o(ptw_device[0]),.mem_ready_i(ptw_ready[0]),
      .mem_address_o(ptw_address[0]),.mem_response_valid_i(ptw_rsp_valid[0]),
      .mem_response_ready_o(ptw_rsp_ready[0]),.mem_response_data_i(ptw_data[0]),.mem_response_error_i(ptw_error[0]));
    assign imem_req_addr_o=PADDR_WIDTH'(if_bus_address);
    for(genvar p=0;p<IFU_PMP_PORTS;p++)
      assign ifu_physical_pmp_address[p]=PADDR_WIDTH'(if_physical)+PADDR_WIDTH'(p*2);
    rv23_ptw_arbiter #(.ADDRESS_WIDTH(PADDR_WIDTH),.PORTS(5)) u_ptw (
      .clk_i,.rst_ni,.req_valid_i(ptw_valid),.req_device_i(ptw_device),.req_ready_o(ptw_ready),
      .req_address_i(ptw_address),.rsp_valid_o(ptw_rsp_valid),.rsp_ready_i(ptw_rsp_ready),
      .rsp_data_o(ptw_data),.rsp_error_o(ptw_error),.pmpcfg_i(pmpcfg),.pmpaddr_i(pmpaddr),
      .bus_valid_o(ptw_req_valid_o),.bus_ready_i(ptw_req_ready_i),.bus_address_o(ptw_req_address_o),
      .bus_device_o(ptw_req_device_o),.bus_rsp_valid_i(ptw_rsp_valid_i),.bus_rsp_ready_o(ptw_rsp_ready_o),
      .bus_rsp_data_i(ptw_rsp_data_i),.bus_rsp_error_i(ptw_rsp_error_i),.idle_o(ptw_idle));
  end else begin:g_no_mmu
  assign imem_req_valid_o = rst_ni && fe_imem_req_valid;
  assign imem_req_addr_o = fe_imem_req_addr;
  assign imem_req_id_o = fe_imem_req_id;
  assign imem_req_epoch_o = fe_imem_req_epoch;
  assign fe_imem_req_ready = rst_ni && imem_req_ready_i;
  assign fe_imem_rsp_valid = imem_rsp_valid_i;
  assign fe_imem_rsp_id = imem_rsp_id_i;
  assign fe_imem_rsp_epoch = imem_rsp_epoch_i;
  assign fe_imem_rsp_data = imem_rsp_data_i;
  assign fe_imem_rsp_resp = imem_rsp_resp_i;
  assign imem_rsp_ready_o = fe_imem_rsp_ready;

    assign ifu_physical_pmp_address=ifu_pmp_check_address;
    assign fe_imem_rsp_fault_cause=6'd1;
      assign fe_imem_guest_address=0;assign fe_imem_implicit_guest_access=0;
    assign imem_req_device_o=0;assign if_translation_idle=1;assign ptw_idle=1;
    assign ptw_valid[0]=0;assign ptw_device[0]=0;assign ptw_address[0]=0;assign ptw_rsp_ready[0]=0;
    assign ptw_ready=0;assign ptw_rsp_valid=0;assign ptw_data=0;assign ptw_error=0;
    assign ptw_req_valid_o=0;assign ptw_req_device_o=0;assign ptw_req_address_o=0;assign ptw_rsp_ready_o=0;
  end

  always_comb begin
    for (int unsigned lane = 0; lane < 2; lane++) begin
      backend_dmem_req_ready[lane] = rst_ni &&
        (!dmem_hold_valid_q[lane] || dmem_req_ready_i[lane]);

      dmem_req_valid_o[lane] = rst_ni &&
        (dmem_hold_valid_q[lane] || backend_dmem_req_valid[lane]);
      dmem_req_id_o[lane] = dmem_hold_valid_q[lane] ?
        dmem_hold_id_q[lane] : backend_dmem_req_id[lane];
      dmem_req_write_o[lane] = dmem_hold_valid_q[lane] ?
        dmem_hold_write_q[lane] : backend_dmem_req_write[lane];
      dmem_req_addr_o[lane] = dmem_hold_valid_q[lane] ?
        dmem_hold_addr_q[lane] : backend_dmem_req_addr[lane];
      dmem_req_size_o[lane] = dmem_hold_valid_q[lane] ?
        dmem_hold_size_q[lane] : backend_dmem_req_size[lane];
      dmem_req_wdata_o[lane] = dmem_hold_valid_q[lane] ?
        dmem_hold_wdata_q[lane] : backend_dmem_req_wdata[lane];
      dmem_req_wstrb_o[lane] = dmem_hold_valid_q[lane] ?
        dmem_hold_wstrb_q[lane] : backend_dmem_req_wstrb[lane];
      dmem_req_priv_o[lane] = dmem_hold_valid_q[lane] ?
        dmem_hold_priv_q[lane] : backend_dmem_req_priv[lane];
      dmem_req_rob_seq_o[lane] = dmem_hold_valid_q[lane] ?
        dmem_hold_rob_seq_q[lane] : backend_dmem_req_rob_seq[lane];
      dmem_req_committed_o[lane] = dmem_hold_valid_q[lane] ?
        dmem_hold_committed_q[lane] : backend_dmem_req_committed[lane];
      dmem_req_device_o[lane] = dmem_hold_valid_q[lane] ?
        dmem_hold_device_q[lane] : backend_dmem_req_device[lane];
    end
  end

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      dmem_hold_valid_q <= '0;
      dmem_hold_id_q <= '0;
      dmem_hold_write_q <= '0;
      dmem_hold_addr_q <= '0;
      dmem_hold_size_q <= '0;
      dmem_hold_wdata_q <= '0;
      dmem_hold_wstrb_q <= '0;
      dmem_hold_priv_q <= '0;
      dmem_hold_rob_seq_q <= '0;
      dmem_hold_committed_q <= '0;
      dmem_hold_device_q <= '0;
    end else begin
      for (int unsigned lane = 0; lane < 2; lane++) begin
        if (backend_dmem_req_ready[lane]) begin
          // With an empty entry and ready downstream, the fall-through request
          // is consumed directly.  If an old held request is consumed, capture
          // a simultaneously accepted replacement for the following cycle.
          dmem_hold_valid_q[lane] <= backend_dmem_req_valid[lane] &&
            (dmem_hold_valid_q[lane] || !dmem_req_ready_i[lane]);
          if (backend_dmem_req_valid[lane] &&
              (dmem_hold_valid_q[lane] || !dmem_req_ready_i[lane])) begin
            dmem_hold_id_q[lane] <= backend_dmem_req_id[lane];
            dmem_hold_write_q[lane] <= backend_dmem_req_write[lane];
            dmem_hold_addr_q[lane] <= backend_dmem_req_addr[lane];
            dmem_hold_size_q[lane] <= backend_dmem_req_size[lane];
            dmem_hold_wdata_q[lane] <= backend_dmem_req_wdata[lane];
            dmem_hold_wstrb_q[lane] <= backend_dmem_req_wstrb[lane];
            dmem_hold_priv_q[lane] <= backend_dmem_req_priv[lane];
            dmem_hold_rob_seq_q[lane] <= backend_dmem_req_rob_seq[lane];
            dmem_hold_committed_q[lane] <=
              backend_dmem_req_committed[lane];
            dmem_hold_device_q[lane] <= backend_dmem_req_device[lane];
          end
        end
      end
    end
  end

  rv_backend #(
    .XLEN            (XLEN),
    .PADDR_WIDTH     (PADDR_WIDTH),
    .MEM_DATA_WIDTH  (MEM_DATA_WIDTH),
    .HAS_C           (HAS_C),
    .HAS_F           (HAS_F),
    .HAS_SMODE       (HAS_SMODE),
    .HAS_V(HAS_V),.HAS_H(HAS_H),.HAS_ZAWRS(HAS_ZAWRS),.HAS_ZIMOP(HAS_ZIMOP),.HAS_ZCMOP(HAS_ZCMOP),.HAS_ZCB(HAS_ZCB),.HAS_SVINVAL(HAS_SVINVAL),.HAS_SSNPM(HAS_SSNPM),.HAS_D(HAS_D),.HAS_ZFHMIN(HAS_ZFHMIN),.HAS_ZFA(HAS_ZFA),.HAS_MISALIGNED(HAS_MISALIGNED),.HAS_CBO(HAS_CBO),.HAS_A(HAS_A), .HAS_B(HAS_B), .HAS_ZICOND(HAS_ZICOND), .HAS_MMU(HAS_MMU),
    .ROB_ENTRIES     (ROB_ENTRIES),
    .ROB_SEQ_WIDTH   (ROB_SEQ_WIDTH),
    .INT_PHYS_REGS   (INT_PHYS_REGS),
    .FP_PHYS_REGS    (FP_PHYS_REGS),
    .INT_IQ_ENTRIES  (INT_IQ_ENTRIES),
    .MEM_IQ_ENTRIES  (MEM_IQ_ENTRIES),
    .FP_IQ_ENTRIES   (FP_IQ_ENTRIES),
    .LQ_ENTRIES      (LQ_ENTRIES),
    .SQ_ENTRIES      (SQ_ENTRIES),
    .STORE_BUFFER_ENTRIES (STORE_BUFFER_ENTRIES),
    .BR_CHECKPOINTS  (BR_CHECKPOINTS),
    .EARLY_LOAD_SELECT(EARLY_LOAD_SELECT), .AGU_LOAD_BYPASS(AGU_LOAD_BYPASS),
    .COMPATIBLE_PAIR_SELECT(COMPATIBLE_PAIR_SELECT),
    .BRANCH_TAG_PIPELINE(BRANCH_TAG_PIPELINE),
    .DIV_TAG_PIPELINE(DIV_TAG_PIPELINE),
    .INT_ISSUE_PIPELINE(INT_ISSUE_PIPELINE),
    .SYSTEM_RESULT_PIPELINE(SYSTEM_RESULT_PIPELINE),
    .ROB_COMPLETION_PIPELINE(ROB_COMPLETION_PIPELINE),
    .LSU_VALIDATION_PIPELINE(LSU_VALIDATION_PIPELINE),
    .AGU_EA_PRECOMPUTE(AGU_EA_PRECOMPUTE),
    .FPU_LATENCY(FPU_LATENCY),
    .ITIM_BASE_ADDR  (ITIM_BASE_ADDR),
    .ITIM_SIZE_KB    (ITIM_SIZE_KB),
    .DTIM_BASE_ADDR  (DTIM_BASE_ADDR),
    .DTIM_SIZE_KB    (DTIM_SIZE_KB),
    .RESET_VECTOR    (RESET_VECTOR),
    .TRAP_VECTOR     (TRAP_VECTOR)
  ) u_backend (
    .cbo_memory_read_o,.cbo_memory_device_o,.cbo_memory_use_dcache_o,.cbo_memory_size_o,.cbo_memory_data_o,.cbo_memory_strobe_o,.cbo_memory_response_data_i,
    .cbo_write_valid_o,.cbo_write_ready_i,.cbo_write_address_o,.cbo_write_privilege_o,
    .cbo_write_response_valid_i,.cbo_write_response_error_i,.cbo_write_response_ready_o,
    .cbo_cache_invalidate_o,.cbo_cache_invalidate_ready_i,

    .atomic_valid_o,.atomic_ready_i,.atomic_reservation_i,.atomic_address_o,.atomic_operand_o,
    .atomic_operation_o,.atomic_word_o,.atomic_privileged_o,.atomic_clear_o,
    .atomic_response_valid_i,.atomic_response_ready_o,.atomic_data_i,
    .atomic_exception_i,.atomic_cause_i,

    .clk_i,
    .rst_ni,
    .fetch_valid_i       (fe_valid),
    .fetch_ready_o       (fe_ready),
    .fetch_pc_i          (fe_pc),
    .fetch_instr_i       (fe_instr),
    .fetch_inst_len_i    (fe_inst_len),
    .fetch_prediction_i  (fe_prediction),
    .fetch_fault_i       (fe_fetch_fault),
    .fetch_fault_cause_i(fe_fetch_fault_cause),.fetch_fault_address_i(fe_fetch_fault_address),
    .fetch_guest_address_i(fe_fetch_guest_address),.fetch_implicit_guest_access_i(fe_fetch_implicit_guest_access),
    .redirect_valid_o    (redirect_valid),
    .redirect_pc_o       (redirect_pc),
    .dmem_req_valid_o     (backend_dmem_req_valid),
    .dmem_req_ready_i     (backend_dmem_req_ready),
    .dmem_req_id_o        (backend_dmem_req_id),
    .dmem_req_write_o     (backend_dmem_req_write),
    .dmem_req_addr_o      (backend_dmem_req_addr),
    .dmem_req_size_o      (backend_dmem_req_size),
    .dmem_req_wdata_o     (backend_dmem_req_wdata),
    .dmem_req_wstrb_o     (backend_dmem_req_wstrb),
    .dmem_req_priv_o      (backend_dmem_req_priv),
    .dmem_req_rob_seq_o   (backend_dmem_req_rob_seq),
    .dmem_req_committed_o (backend_dmem_req_committed),
    .dmem_req_device_o    (backend_dmem_req_device),
    .dmem_rsp_valid_i,
    .dmem_rsp_ready_o,
    .dmem_rsp_id_i,
    .dmem_rsp_rdata_i,
    .dmem_rsp_resp_i,
    .dmem_rsp_replay_i,
    .irq_software_i,
    .irq_timer_i,
    .irq_external_i,.irq_supervisor_external_i,
    .mstatus_o,.satp_o,.menvcfg_o,.senvcfg_o,.translation_invalidate_i(translation_invalidate),
    .current_virtual_o(current_virtual),.hstatus_o(hstatus),.vsstatus_o(vsstatus),.vsatp_o(vsatp),.hgatp_o(hgatp),.henvcfg_o(henvcfg),
    .cbo_ptw_valid_o(ptw_valid[4]),.cbo_ptw_device_o(ptw_device[4]),
    .cbo_ptw_ready_i(ptw_ready[4]),.cbo_ptw_address_o(ptw_address[4]),
    .cbo_ptw_response_valid_i(ptw_rsp_valid[4]),.cbo_ptw_response_ready_o(ptw_rsp_ready[4]),
    .cbo_ptw_data_i(ptw_data[4]),.cbo_ptw_error_i(ptw_error[4]),
    .atomic_ptw_valid_o(ptw_valid[3]),.atomic_ptw_device_o(ptw_device[3]),
    .atomic_ptw_ready_i(ptw_ready[3]),.atomic_ptw_address_o(ptw_address[3]),
    .atomic_ptw_response_valid_i(ptw_rsp_valid[3]),.atomic_ptw_response_ready_o(ptw_rsp_ready[3]),
    .atomic_ptw_data_i(ptw_data[3]),.atomic_ptw_error_i(ptw_error[3]),
    .ptw_valid_o(ptw_valid[2:1]),.ptw_device_o(ptw_device[2:1]),.ptw_ready_i(ptw_ready[2:1]),
    .ptw_address_o(ptw_address[2:1]),.ptw_response_valid_i(ptw_rsp_valid[2:1]),
    .ptw_response_ready_o(ptw_rsp_ready[2:1]),.ptw_data_i(ptw_data[2:1]),.ptw_error_i(ptw_error[2:1]),
    .mtime_i,
    .debug_halt_req_i,
    .debug_drained_o(backend_debug_drained),
    .trace_valid_o,
    .trace_pc_o,
    .trace_instr_o,
    .trace_rd_o,
    .trace_rd_write_o,
    .trace_rd_fp_o,
    .trace_rd_wdata_o,
    .trace_trap_o,
    .trace_cause_o,
    .trace_tval_o,
    .current_privilege_o (current_privilege),
    .pmpcfg_o            (pmpcfg),
    .pmpaddr_o           (pmpaddr),
    .bp_resolve_valid_o  (bp_resolve_valid),
    .bp_resolve_pc_o     (bp_resolve_pc),
    .bp_resolve_instruction_o(bp_resolve_instruction),
    .bp_resolve_inst_len_o(bp_resolve_inst_len),
    .bp_resolve_taken_o  (bp_resolve_taken),
    .bp_resolve_target_o (bp_resolve_target),
    .bp_resolve_mispredict_o(bp_resolve_mispredict),
    .bp_resolve_prediction_o(bp_resolve_prediction),
    .bp_commit_valid_o   (bp_commit_valid),
    .bp_commit_pc_o      (bp_commit_pc),
    .bp_commit_instruction_o(bp_commit_instruction),
    .bp_commit_inst_len_o(bp_commit_inst_len),
    .bp_commit_taken_o   (bp_commit_taken)
  );

  logic unused_ifu_pmp;
  always_comb unused_ifu_pmp = (^ifu_pmp_matched) ^
                               (^ifu_pmp_fault_address);

`ifndef SYNTHESIS
  for (genvar parcel = 0; parcel < IFU_PMP_PORTS; parcel++) begin : g_pmp_assert
    property p_pmp_is_two_byte_instruction_parcel;
      @(posedge clk_i) disable iff (!rst_ni)
        ifu_pmp_check_valid[parcel] |->
          (ifu_pmp_check_size[parcel] == 3'd1) &&
          (ifu_pmp_check_access[parcel] == 3'b100);
    endproperty
    assert property (p_pmp_is_two_byte_instruction_parcel);
  end
`endif

endmodule

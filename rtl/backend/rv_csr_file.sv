module rv_csr_file #(
  parameter int unsigned XLEN = 32,
  parameter int unsigned PADDR_WIDTH = XLEN,
  parameter int unsigned IMPLEMENTED_PADDR_WIDTH=PADDR_WIDTH,
  parameter bit HAS_A=0,
  parameter bit HAS_V=0,
  parameter bit HAS_H=0,
  parameter int unsigned HPM_COUNTERS=(XLEN==64?4:0),
  parameter bit HAS_CBO=0,
  parameter bit HAS_D=0,HAS_ZFHMIN=0,HAS_ZFA=0,
  parameter bit HAS_SSNPM=0,
  parameter bit HAS_C = 1'b1,
  parameter bit HAS_F = 1'b1,
  parameter bit HAS_SMODE = 1'b0,
  parameter bit HAS_B = 1'b0,
  parameter int unsigned PMP_ENTRIES = 8,
  parameter logic [XLEN-1:0] RESET_MTVEC = 'h8000_0000,
  parameter logic [XLEN-1:0] HART_ID = '0,
  localparam int unsigned PMP_ADDR_WIDTH = PADDR_WIDTH - 2
) (
  input  logic                         clk_i,
  input  logic                         rst_ni,

  // A CSR instruction is evaluated only at the ROB head.  csr_commit_i is
  // the architectural commit edge; evaluation alone never changes state.
  input  logic                         csr_valid_i,
  input  logic                         csr_execute_i,
  input  logic                         csr_commit_i,
  input  logic [11:0]                  csr_addr_i,
  input  rv_ooo_pkg::csr_cmd_e         csr_cmd_i,
  input  logic [XLEN-1:0]              csr_operand_i,
  input  logic                         csr_rs1_is_zero_i,
  output logic                         csr_ready_o,
  output logic [XLEN-1:0]              csr_rdata_o,
  output logic                         csr_illegal_o,
  output logic                         csr_write_effect_o,
  output logic [5:0] csr_exception_cause_o,

  // Precise trap and xRET ports.  trap_cause_i contains the low cause code;
  // the interrupt bit is supplied separately and encoded into mcause here.
  input  logic                         trap_valid_i,
  output logic                         trap_ready_o,
  input  logic [XLEN-1:0]              trap_pc_i,
  input  logic [5:0]                   trap_cause_i,
  input  logic [XLEN-1:0]              trap_tval_i,
  input  logic                         trap_is_interrupt_i,
  input logic [63:0] trap_guest_address_i=0,
  input logic trap_implicit_guest_access_i=0,trap_guest_va_i=0,
  input  logic [XLEN-1:0]              trap_next_pc_i,
  output logic [XLEN-1:0]              trap_vector_o,

  input  logic                         mret_valid_i,
  input  logic                         mret_commit_i,
  output logic                         mret_ready_o,
  output logic [XLEN-1:0]              mret_pc_o,
  output logic                         mret_illegal_o,

  input  logic                         sret_valid_i = 1'b0,
  input  logic                         sret_commit_i = 1'b0,
  output logic [XLEN-1:0]              sret_pc_o,
  output logic                         sret_illegal_o,
  output logic [5:0] sret_cause_o,sfence_cause_o,wfi_cause_o,
  input logic                          sfence_valid_i = 1'b0,
  output logic                         sfence_illegal_o,

  input  logic                         wfi_valid_i,
  output logic                         wfi_illegal_o,
  output logic                         wfi_wake_o,

  input  logic                         irq_software_i,
  input  logic                         irq_timer_i,
  input  logic                         irq_external_i,
  input  logic                         irq_supervisor_external_i = 1'b0,
  input  logic [63:0]                  mtime_i,
  output logic                         interrupt_pending_o,
  output logic [5:0]                   interrupt_cause_o,

  input  logic [1:0]                   retire_count_i,
  input  logic                         fp_state_write_i=0,
  input logic vector_state_write_i=0,
  input logic [63:0] vector_vl_i=0,vector_vtype_i=0,vector_vstart_i=0,
  input logic [1:0] vector_vxrm_i=0,
  input logic vector_vxsat_i=0,
  output logic vector_csr_write_o,
  output logic [11:0] vector_csr_address_o,
  output logic [63:0] vector_csr_data_o,
  input  logic                         fflags_accrue_valid_i,
  input  logic [4:0]                   fflags_accrue_i,
  input  logic                         flush_all_i,

  output rv_ooo_pkg::privilege_e       privilege_o,
  output logic [XLEN-1:0]              mstatus_o,
  output logic [XLEN-1:0]              mtvec_o,
  output logic [XLEN-1:0]              mepc_o,
  output logic [2:0]                   frm_o,
  output logic [4:0]                   fflags_o,
  output logic [63:0]                  satp_o,menvcfg_o,senvcfg_o,
  output logic virtual_o,
  output logic [63:0] hstatus_o,vsstatus_o,vsatp_o,hgatp_o,henvcfg_o,
  output logic [PMP_ENTRIES-1:0][7:0] pmpcfg_o,
  output logic [PMP_ENTRIES-1:0][PMP_ADDR_WIDTH-1:0] pmpaddr_o
);

  import rv_ooo_pkg::*;

  localparam int unsigned MSTATUS_MIE  = 3;
  localparam int unsigned MSTATUS_MPIE = 7;
  localparam int unsigned MSTATUS_MPP_LO = 11;
  localparam int unsigned MSTATUS_FS_LO = 13;
  localparam int unsigned MSTATUS_MPRV = 17;
  localparam int unsigned MSTATUS_TW   = 21;
  localparam int unsigned MIP_MSIP = 3;
  localparam int unsigned MIP_MTIP = 7;
  localparam int unsigned MIP_MEIP = 11;

  privilege_e current_priv_q;
  logic [XLEN-1:0] mstatus_q;
  logic [XLEN-1:0] mie_q;
  logic [XLEN-1:0] mtvec_q;
  logic [XLEN-1:0] mscratch_q;
  logic [XLEN-1:0] mepc_q;
  logic [XLEN-1:0] mcause_q;
  logic [XLEN-1:0] mtval_q;
  logic [XLEN-1:0] mcounteren_q;
  logic [XLEN-1:0] medeleg_q,mideleg_q,stvec_q,sscratch_q,sepc_q,scause_q,stval_q,scounteren_q;
  logic [XLEN-1:0] software_mip_q;
  logic [63:0] satp_q,menvcfg_q,senvcfg_q,stimecmp_q;
  logic [XLEN-1:0] mcountinhibit_q;
  logic trap_to_s;
  logic [XLEN-1:0] sstatus_mask,sstatus_write_mask;
  logic [XLEN-1:0] enabled_machine_interrupts,enabled_supervisor_interrupts;
  localparam logic [31:0] HPM_MASK=((32'b1<<HPM_COUNTERS)-1)<<3;
  localparam logic [31:0] COUNTER_ENABLE_MASK=32'h7|HPM_MASK;
  localparam logic [XLEN-1:0] S_INTERRUPT_MASK=XLEN'('h222)|(HPM_COUNTERS!=0?XLEN'('h2000):XLEN'(0));
  localparam logic [XLEN-1:0] M_INTERRUPT_MASK=XLEN'('h888);
  logic [XLEN-1:0] delegated_supervisor_mask;
  // mideleg also includes the H interrupt bits, which belong to hie/hip.
  assign delegated_supervisor_mask = mideleg_q & S_INTERRUPT_MASK;
  localparam logic [XLEN-1:0] MEDELEG_MASK=XLEN'(HAS_H?64'hf0b7ff:64'hb3ff);
  logic [63:0] mcycle_q;
  logic [63:0] minstret_q;
  logic [4:0] fflags_q;
  logic [2:0] frm_q;
  logic [7:0] pmpcfg_q [0:PMP_ENTRIES-1];
  logic [PMP_ADDR_WIDTH-1:0] pmpaddr_q [0:PMP_ENTRIES-1];
  logic csr_pending_q;
  logic [11:0] csr_pending_addr_q;
  logic csr_pending_write_q;
  logic [XLEN-1:0] csr_pending_wdata_q;

  logic [XLEN-1:0] mip_value;
  logic [XLEN-1:0] misa_value;
  logic [XLEN-1:0] csr_read_value;
  logic [XLEN-1:0] csr_write_value;
  logic [XLEN-1:0] mstatus_read_value;
  logic csr_exists;
  logic csr_counter_access;
  logic csr_fp_state_access;
  logic csr_vector_state_access;
  logic csr_read_only;
  logic csr_privilege_ok;
  logic csr_write_intent;
  logic [XLEN-1:0] enabled_interrupts;
  logic interrupt_global_enable;
  logic h_selected,h_csr_exception,h_stateen_selected,h_stateen_exception,h_env_exception;
  logic h_to_vs,h_mpv,h_gva,h_xret_virtual;
  logic [5:0] h_cause,h_stateen_cause,h_env_cause;
  logic [63:0] h_data,h_stateen_data,h_hedeleg,h_hideleg,h_counteren,h_hip,h_hie,h_delta;
  logic [63:0] h_trap_vector,h_return_pc,h_mtval2,h_mtinst;
  logic [1:0] h_return_privilege;
  logic [XLEN-1:0] enabled_vs_interrupts;
  logic h_csr_virtual_fault;
  logic [11:0] h_access_address;
  logic h_access_valid,h_access_commit;
  wire [31:0][63:0] hpm_counter,hpm_event;
  logic [31:0] hpm_overflow;
  logic hpm_pending;
  logic hpm_arch_write;
  assign hpm_arch_write=h_access_commit && !(trap_valid_i && trap_ready_o) &&
    !(mret_valid_i && mret_commit_i && !mret_illegal_o) &&
    !(sret_valid_i && sret_commit_i && !sret_illegal_o);
  if(HPM_COUNTERS!=0)begin:g_hpm
    rv_hpm_counters #(.XLEN(XLEN),.COUNTERS(HPM_COUNTERS),.HAS_SMODE(HAS_SMODE),.HAS_H(HAS_H)) u_counters(
      .clk_i,.rst_ni,.privilege_i(current_priv_q),.virtual_i(virtual_o),.retire_count_i,
      .inhibit_i(32'(mcountinhibit_q)),.write_valid_i(hpm_arch_write),.write_address_i(csr_pending_addr_q),
      .write_data_i(csr_pending_wdata_q),
      .pending_write_i(hpm_arch_write && (csr_pending_addr_q==12'h344 ||
        (csr_pending_addr_q==12'h144 && !virtual_o && mideleg_q[13]))),
      .pending_data_i(csr_pending_wdata_q[13]),.pending_o(hpm_pending),
      .counter_mask_o(),.overflow_o(hpm_overflow),.counter_o(hpm_counter),.event_o(hpm_event));
  end else begin:g_no_hpm
    assign hpm_counter=0;assign hpm_event=0;assign hpm_overflow=0;assign hpm_pending=0;
  end
  assign h_access_commit=csr_commit_i && csr_pending_q && csr_pending_write_q;
  assign h_access_valid=csr_valid_i || h_access_commit;
  assign h_access_address=h_access_commit?csr_pending_addr_q:csr_addr_i;
  assign trap_to_s=HAS_SMODE && current_priv_q!=PRIV_M && int'(trap_cause_i)<XLEN &&
    (trap_is_interrupt_i?mideleg_q[trap_cause_i]:medeleg_q[trap_cause_i]);
  if(HAS_H)begin:g_hypervisor
    rv_hypervisor_csrs #(.COUNTER_MASK(64'(COUNTER_ENABLE_MASK))) u_h(
      .clk_i,.rst_ni,.csr_valid_i(h_access_valid),.csr_commit_write_i(h_access_commit),
      .csr_write_intent_i((csr_cmd_i==CSR_CMD_WRITE) ||
        ((csr_cmd_i==CSR_CMD_SET || csr_cmd_i==CSR_CMD_CLEAR) && !csr_rs1_is_zero_i)),
      .csr_address_i(h_access_address),.csr_write_data_i(64'(csr_pending_wdata_q)),.privilege_i(current_priv_q),
      .mstatus_i(64'(mstatus_q)),.menvcfg_i(menvcfg_q),.mcounteren_i(64'(mcounteren_q)),.mtime_i,
      .csr_selected_o(h_selected),.csr_data_o(h_data),.csr_exception_o(h_csr_exception),.csr_cause_o(h_cause),
      .mstatus_commit_write_i(h_access_commit && csr_pending_addr_q==12'h300),
      .mie_commit_write_i(h_access_commit && csr_pending_addr_q==12'h304),
      .mip_commit_write_i(h_access_commit && csr_pending_addr_q==12'h344),.machine_write_data_i(64'(csr_pending_wdata_q)),
      .fp_dirty_i(fp_state_write_i || (fflags_accrue_valid_i && |fflags_accrue_i) ||
        (h_access_commit && csr_pending_addr_q inside {12'h001,12'h002,12'h003})),
      .vector_dirty_i(vector_state_write_i || vector_csr_write_o),
      .trap_commit_i(trap_valid_i && trap_ready_o),.trap_delegated_i(trap_to_s),.trap_interrupt_i(trap_is_interrupt_i),
      .trap_guest_va_i,.trap_cause_i,.trap_pc_i(64'(trap_pc_i)),.trap_next_pc_i(64'(trap_next_pc_i)),
      .trap_tval_i(64'(trap_tval_i)),.trap_guest_address_i,.trap_implicit_guest_access_i,
      .trap_to_vs_o(h_to_vs),.vs_trap_vector_o(h_trap_vector),
      .mret_commit_i(mret_valid_i && mret_commit_i && !mret_illegal_o),
      .sret_commit_i(sret_valid_i && sret_commit_i && !sret_illegal_o),.xret_is_mret_i(mret_valid_i),
      .hs_return_pc_i(64'(sepc_q)),.m_return_pc_i(64'(mepc_q)),.xret_privilege_o(h_return_privilege),
      .xret_virtual_o(h_xret_virtual),.xret_pc_o(h_return_pc),.virtual_o,.mpv_o(h_mpv),.gva_o(h_gva),
      .hstatus_o,.hedeleg_o(h_hedeleg),.hideleg_o(h_hideleg),.henvcfg_o,.hcounteren_o(h_counteren),
      .vsstatus_o,.vsatp_o,.hgatp_o,.hip_o(h_hip),.hie_o(h_hie),.htimedelta_o(h_delta),.mtval2_o(h_mtval2),.mtinst_o(h_mtinst));
    rv_hypervisor_stateen u_stateen(.clk_i,.rst_ni,.csr_valid_i(h_access_valid),.csr_commit_write_i(h_access_commit),
      .csr_address_i(h_access_address),.csr_write_data_i(64'(csr_pending_wdata_q)),.privilege_i(current_priv_q),.virtual_i(virtual_o),
      .csr_selected_o(h_stateen_selected),.csr_data_o(h_stateen_data),.csr_exception_o(h_stateen_exception),
      .csr_cause_o(h_stateen_cause),.envcfg_exception_o(h_env_exception),.envcfg_cause_o(h_env_cause));
  end else begin:g_no_hypervisor
    assign h_selected=0;assign h_data=0;assign h_csr_exception=0;assign h_cause=2;
    assign h_stateen_selected=0;assign h_stateen_data=0;assign h_stateen_exception=0;assign h_stateen_cause=2;
    assign h_env_exception=0;assign h_env_cause=2;assign h_to_vs=0;assign h_mpv=0;assign h_gva=0;
    assign h_xret_virtual=0;assign h_return_privilege=0;assign h_return_pc=0;assign h_trap_vector=0;
    assign virtual_o=0;assign hstatus_o=0;assign vsstatus_o=0;assign vsatp_o=0;assign hgatp_o=0;assign henvcfg_o=0;
    assign h_hedeleg=0;assign h_hideleg=0;assign h_counteren=0;assign h_hip=0;assign h_hie=0;assign h_delta=0;
    assign h_mtval2=0;assign h_mtinst=0;
  end

  // Only the low two sum bits depend on the late 0..3 increment. Upper-bit
  // all-ones prefixes are prepared from stored value before that carry.
  // Counter writes retain priority; no state, latency or interface change.
  function automatic logic [63:0] increment_counter(
    input logic [63:0] value,
    input logic [1:0] increment
  );
    logic [61:0] upper_ones_prefix;
    logic [61:0] ones_from_two;
    logic [61:0] ones_from_one;
    logic [61:0] ones_from_zero;
    logic [61:0] carry;
    upper_ones_prefix = value[63:2];
    for (int stride = 1; stride < 62; stride *= 2)
      upper_ones_prefix &= (upper_ones_prefix << stride) |
                           ((62'd1 << stride) - 62'd1);
    ones_from_two = {upper_ones_prefix[60:0],1'b1};
    ones_from_one = ones_from_two & {62{value[1]}};
    ones_from_zero = ones_from_one & {62{value[0]}};
    carry = (ones_from_one & {62{increment[1]}}) |
            (ones_from_zero & {62{increment[0]}}) |
            (ones_from_two & {62{value[0] & increment[0] & increment[1]}});
    increment_counter[0] = value[0] ^ increment[0];
    increment_counter[1] = value[1] ^ increment[1] ^ (value[0] & increment[0]);
    increment_counter[63:2] = value[63:2] ^ carry;
  endfunction

  function automatic logic [XLEN-1:0] build_misa;
    logic [XLEN-1:0] value;
    value = '0;
    value[0]  = HAS_A; // A
    value[1]  = HAS_B; // B = Zba/Zbb/Zbs
    value[2]  = HAS_C; // C
    value[3]  = HAS_F && HAS_D; // D
    value[5]  = HAS_F; // F
    value[8]  = 1'b1; // I
    value[12] = 1'b1; // M
    value[20] = 1'b1; // U
    value[21] = HAS_V; // V (architectural integration is selected by caller)
    value[7] = HAS_H;
    if (HAS_SMODE)
      value[18] = 1'b1;
    value[XLEN-1 -: 2] = (XLEN == 32) ? 2'b01 : 2'b10;
    return value;
  endfunction

  function automatic logic [XLEN-1:0] sanitize_mstatus(
    input logic [XLEN-1:0] value
  );
    logic [XLEN-1:0] result;
    logic [1:0] requested_mpp;
    result = '0;
    result[MSTATUS_MIE] = value[MSTATUS_MIE];
    result[MSTATUS_MPIE] = value[MSTATUS_MPIE];
    requested_mpp = value[MSTATUS_MPP_LO +: 2];
    if (requested_mpp == PRIV_M)
      result[MSTATUS_MPP_LO +: 2] = PRIV_M;
    else if (HAS_SMODE && (requested_mpp == PRIV_S))
      result[MSTATUS_MPP_LO +: 2] = PRIV_S;
    else
      result[MSTATUS_MPP_LO +: 2] = PRIV_U;
    result[MSTATUS_FS_LO +: 2] = value[MSTATUS_FS_LO +: 2];
    if(HAS_V)result[10:9]=value[10:9];
    result[MSTATUS_MPRV] = value[MSTATUS_MPRV];
    result[MSTATUS_TW] = value[MSTATUS_TW];
    if(HAS_SMODE) begin
      result[1]=value[1];result[5]=value[5];result[8]=value[8];
      result[18]=value[18];result[19]=value[19];result[20]=value[20];result[22]=value[22];
      if(XLEN==64) begin result|=XLEN'(64'h0000000a00000000);end
    end
    return result;
  endfunction

  function automatic logic pmp_address_locked(input int unsigned index);
    logic locked;
    locked = pmpcfg_q[index][7];
    if ((index + 1) < PMP_ENTRIES)
      locked |= pmpcfg_q[index+1][7] &&
                (pmpcfg_q[index+1][4:3] == 2'b01);
    return locked;
  endfunction

  always_comb begin
    misa_value = build_misa();
    mip_value = '0;
    mip_value[MIP_MSIP] = irq_software_i;
    mip_value[MIP_MTIP] = irq_timer_i;
    mip_value[MIP_MEIP] = irq_external_i;
    mip_value[13]=hpm_pending;
    if(HAS_H)mip_value|=XLEN'(h_hip);
    if(HAS_SMODE) begin
      mip_value|=software_mip_q & S_INTERRUPT_MASK;
      mip_value[9]|=irq_supervisor_external_i;
      if(menvcfg_q[63]) mip_value[5]=mtime_i>=stimecmp_q;
    end

    mstatus_read_value = mstatus_q;
    if(HAS_H)mstatus_read_value|=(XLEN'(h_mpv)<<39)|(XLEN'(h_gva)<<38);
    if (mstatus_q[MSTATUS_FS_LO +: 2] == 2'b11 || (HAS_V && mstatus_q[10:9]==3))
      mstatus_read_value[XLEN-1] = 1'b1;
    if(HAS_SMODE && XLEN==64) mstatus_read_value|=XLEN'(64'h0000000a00000000);
    sstatus_write_mask=XLEN'('h000c6122);
    if(HAS_V)sstatus_write_mask|=XLEN'('h600);
    sstatus_mask=sstatus_write_mask | (XLEN'(1)<<(XLEN-1));
    if(XLEN==64) sstatus_mask|=XLEN'(64'h0000000300000000);

    csr_exists = 1'b1;
    csr_counter_access = 1'b0;
    csr_fp_state_access = 1'b0;
    csr_vector_state_access=0;
    csr_read_value = '0;
    case (csr_addr_i)
      12'h001: begin
        csr_read_value = XLEN'(fflags_q);
        csr_fp_state_access = 1'b1;
      end
      12'h002: begin
        csr_read_value = XLEN'(frm_q);
        csr_fp_state_access = 1'b1;
      end
      12'h003: begin
        csr_read_value = XLEN'({frm_q, fflags_q});
        csr_fp_state_access = 1'b1;
      end
      12'h008:begin csr_exists=HAS_V;csr_vector_state_access=1;csr_read_value=XLEN'(vector_vstart_i);end
      12'h009:begin csr_exists=HAS_V;csr_vector_state_access=1;csr_read_value=XLEN'(vector_vxsat_i);end
      12'h00a:begin csr_exists=HAS_V;csr_vector_state_access=1;csr_read_value=XLEN'(vector_vxrm_i);end
      12'h00f:begin csr_exists=HAS_V;csr_vector_state_access=1;csr_read_value=XLEN'({vector_vxrm_i,vector_vxsat_i});end
      12'hc20:begin csr_exists=HAS_V;csr_vector_state_access=1;csr_read_value=XLEN'(vector_vl_i);end
      12'hc21:begin csr_exists=HAS_V;csr_vector_state_access=1;csr_read_value=XLEN'(vector_vtype_i);end
      12'hc22:begin csr_exists=HAS_V;csr_vector_state_access=1;csr_read_value=XLEN'(16);end
      12'h300: csr_read_value = mstatus_read_value;
      12'h100: begin csr_exists=HAS_SMODE;csr_read_value=mstatus_read_value & sstatus_mask;end
      12'h104: begin csr_exists=HAS_SMODE;csr_read_value=mie_q & delegated_supervisor_mask;end
      12'h105: begin csr_exists=HAS_SMODE;csr_read_value=stvec_q;end
      12'h106: begin csr_exists=HAS_SMODE;csr_read_value=scounteren_q;end
      12'h10a: begin csr_exists=HAS_SMODE;csr_read_value=XLEN'(senvcfg_q);end
      12'h140: begin csr_exists=HAS_SMODE;csr_read_value=sscratch_q;end
      12'h141: begin csr_exists=HAS_SMODE;csr_read_value=sepc_q;end
      12'h142: begin csr_exists=HAS_SMODE;csr_read_value=scause_q;end
      12'h143: begin csr_exists=HAS_SMODE;csr_read_value=stval_q;end
      12'h144: begin csr_exists=HAS_SMODE;csr_read_value=mip_value & delegated_supervisor_mask;end
      12'h14d:begin
        csr_exists=HAS_SMODE && XLEN==64;
        if(current_priv_q!=PRIV_M && (!menvcfg_q[63] || !mcounteren_q[1])) csr_exists=0;
        csr_read_value=XLEN'(stimecmp_q);
      end
      12'h180:begin
        csr_exists=HAS_SMODE && XLEN==64 && !(current_priv_q==PRIV_S && mstatus_q[20]);
        csr_read_value=XLEN'(satp_q);
      end
      12'h302:begin csr_exists=HAS_SMODE;csr_read_value=medeleg_q;end
      12'h303:begin csr_exists=HAS_SMODE;csr_read_value=mideleg_q;end
      12'h30a:begin csr_exists=HAS_SMODE;csr_read_value=XLEN'(menvcfg_q);end
      12'h320:csr_read_value=mcountinhibit_q;
      12'hda0:begin
        csr_exists=HAS_SMODE;
        csr_read_value=XLEN'(hpm_overflow & (current_priv_q==PRIV_M?32'hffffffff:
          (32'(mcounteren_q)&(virtual_o?32'(h_counteren):32'hffffffff))));
      end
      12'h301: csr_read_value = misa_value;
      12'h304: csr_read_value = mie_q | XLEN'(h_hie);
      12'h305: csr_read_value = mtvec_q;
      12'h306: csr_read_value = mcounteren_q;
      12'h340: csr_read_value = mscratch_q;
      12'h341: csr_read_value = mepc_q;
      12'h342: csr_read_value = mcause_q;
      12'h343: csr_read_value = mtval_q;
      12'h344: csr_read_value = mip_value;
      12'hB00: csr_read_value = XLEN'(mcycle_q);
      12'hB02: csr_read_value = XLEN'(minstret_q);
      12'hB80: begin
        csr_exists = (XLEN == 32);
        csr_read_value = XLEN'(mcycle_q[63:32]);
      end
      12'hB82: begin
        csr_exists = (XLEN == 32);
        csr_read_value = XLEN'(minstret_q[63:32]);
      end
      12'hC00: begin
        csr_counter_access = 1'b1;
        csr_read_value = XLEN'(mcycle_q);
      end
      12'hC01: begin
        csr_counter_access = 1'b1;
        csr_read_value = XLEN'(mtime_i+(virtual_o?h_delta:64'b0));
      end
      12'hC02: begin
        csr_counter_access = 1'b1;
        csr_read_value = XLEN'(minstret_q);
      end
      12'hC80: begin
        csr_exists = (XLEN == 32);
        csr_counter_access = 1'b1;
        csr_read_value = XLEN'(mcycle_q[63:32]);
      end
      12'hC81: begin
        csr_exists = (XLEN == 32);
        csr_counter_access = 1'b1;
        csr_read_value = XLEN'(mtime_i[63:32]);
      end
      12'hC82: begin
        csr_exists = (XLEN == 32);
        csr_counter_access = 1'b1;
        csr_read_value = XLEN'(minstret_q[63:32]);
      end
      12'hF11, 12'hF12, 12'hF13: csr_read_value = '0;
      12'hF14: csr_read_value = HART_ID;
      // Mandatory machine configuration pointer. No discovery structure is
      // provided by this platform; zero is the architectural encoding for it.
      12'hF15: csr_read_value = '0;
      default: begin
        csr_exists = 1'b0;
        // Absent counters/selectors are RAZ; implemented HPM state is owned
        // by the committed event bank, independently of CSR evaluation.
        if(csr_addr_i>=12'hb03 && csr_addr_i<=12'hb1f)begin
          csr_exists=1;csr_read_value=XLEN'(hpm_counter[csr_addr_i[4:0]]);
        end
        if(csr_addr_i>=12'h323 && csr_addr_i<=12'h33f)begin
          csr_exists=1;csr_read_value=XLEN'(hpm_event[csr_addr_i[4:0]]);
        end
        if(csr_addr_i>=12'hc03 && csr_addr_i<=12'hc1f) begin
          csr_exists=1;csr_counter_access=1;csr_read_value=XLEN'(hpm_counter[csr_addr_i[4:0]]);
        end
        if(XLEN==32 && ((csr_addr_i>=12'hb83 && csr_addr_i<=12'hb9f) ||
                       (csr_addr_i>=12'hc83 && csr_addr_i<=12'hc9f))) begin
          csr_exists=1;csr_counter_access=csr_addr_i[10];csr_read_value=XLEN'(hpm_counter[csr_addr_i[4:0]][63:32]);
        end
        if(XLEN==32 && csr_addr_i>=12'h723 && csr_addr_i<=12'h73f)begin
          csr_exists=1;csr_read_value=XLEN'(hpm_event[csr_addr_i[4:0]][63:32]);
        end
        for (int unsigned cfg_csr = 0; cfg_csr < 4; cfg_csr++) begin
          if (csr_addr_i == (12'h3A0 + cfg_csr)) begin
            csr_exists = (XLEN == 32) || ((cfg_csr & 1) == 0);
            csr_read_value = '0;
            for (int unsigned byte_index = 0;
                 byte_index < (XLEN/8); byte_index++) begin
              // Keep the RV32/RV64 index expressions in separate constant
              // branches.  Reassigning one automatic loop-local index made
              // some synthesis frontends build a false combinational
              // self-loop even though XLEN is an elaboration constant.
              if (XLEN == 32) begin
                if ((cfg_csr * 4 + byte_index) < PMP_ENTRIES)
                  csr_read_value[byte_index*8 +: 8] =
                    pmpcfg_q[cfg_csr * 4 + byte_index];
              end else begin
                if (((cfg_csr / 2) * 8 + byte_index) < PMP_ENTRIES)
                  csr_read_value[byte_index*8 +: 8] =
                    pmpcfg_q[(cfg_csr / 2) * 8 + byte_index];
              end
            end
          end
        end
        // The base PMP register group has 16 entries. Entries beyond the
        // usable comparator bank remain WARL read-as-zero/write-ignored.
        for (int unsigned entry = 0; entry < 16; entry++) begin
          if (csr_addr_i == (12'h3B0 + entry)) begin
            csr_exists = 1'b1;
            if (entry < PMP_ENTRIES)
              csr_read_value = XLEN'(pmpaddr_q[entry]);
          end
        end
      end
    endcase

    if(HAS_H && h_selected)begin csr_exists=1;csr_read_value=XLEN'(h_data);end
    if(HAS_H && h_stateen_selected)begin csr_exists=1;csr_read_value=XLEN'(h_stateen_data);end
    csr_write_intent = (csr_cmd_i == CSR_CMD_WRITE) ||
      (((csr_cmd_i == CSR_CMD_SET) || (csr_cmd_i == CSR_CMD_CLEAR)) &&
       !csr_rs1_is_zero_i);
    case (csr_cmd_i)
      CSR_CMD_WRITE: csr_write_value = csr_operand_i;
      CSR_CMD_SET:   csr_write_value = csr_read_value | csr_operand_i;
      CSR_CMD_CLEAR: csr_write_value = csr_read_value & ~csr_operand_i;
      default:       csr_write_value = csr_read_value;
    endcase
    // SEIP's external wire participates in the read result, but never in
    // the RMW value of its software-owned bit (Privileged ISA 1.13).
    if(csr_addr_i==12'h344 && csr_cmd_i==CSR_CMD_SET)
      csr_write_value[9]=software_mip_q[9] | csr_operand_i[9];
    if(csr_addr_i==12'h344 && csr_cmd_i==CSR_CMD_CLEAR)
      csr_write_value[9]=software_mip_q[9] & ~csr_operand_i[9];

    csr_read_only = (csr_addr_i[11:10] == 2'b11);
    csr_privilege_ok = (current_priv_q >= privilege_e'(csr_addr_i[9:8]));
    if(HAS_H && (h_selected || h_stateen_selected))csr_privilege_ok=1;
    if (csr_counter_access && (current_priv_q != PRIV_M)) begin
      csr_privilege_ok &= mcounteren_q[csr_addr_i[4:0]] &&
        (!HAS_SMODE || current_priv_q!=PRIV_U || scounteren_q[csr_addr_i[4:0]]);
    end

    csr_ready_o = 1'b1;
    csr_rdata_o = csr_read_value;
    csr_illegal_o = csr_valid_i &&
      (!csr_exists || !csr_privilege_ok ||
       (csr_vector_state_access && mstatus_q[10:9]==0) ||
       (csr_fp_state_access &&
        (!HAS_F || (mstatus_q[MSTATUS_FS_LO +: 2] == 2'b00))) ||
       (csr_read_only && csr_write_intent) ||
       (csr_cmd_i == CSR_CMD_NONE));
    csr_exception_cause_o=6'd2;h_csr_virtual_fault=0;
    if(HAS_H)begin
      if(h_selected && h_csr_exception)begin csr_illegal_o=csr_valid_i;csr_exception_cause_o=h_cause;end
      else if(h_stateen_selected && h_stateen_exception)begin csr_illegal_o=csr_valid_i;csr_exception_cause_o=h_stateen_cause;end
      else if(csr_addr_i==12'h10a && h_env_exception)begin csr_illegal_o=csr_valid_i;csr_exception_cause_o=h_env_cause;end
      else if(virtual_o && current_priv_q==PRIV_U && csr_exists && csr_addr_i[9:8]==1 &&
              !(csr_read_only && csr_write_intent))h_csr_virtual_fault=1;
      if(virtual_o && csr_exists && csr_counter_access && !(csr_read_only && csr_write_intent) &&
         mcounteren_q[csr_addr_i[4:0]] && (!h_counteren[csr_addr_i[4:0]] ||
         (current_priv_q==PRIV_U && !scounteren_q[csr_addr_i[4:0]])))h_csr_virtual_fault=1;
      if(h_csr_virtual_fault)begin csr_illegal_o=csr_valid_i;csr_exception_cause_o=22;end
      if(virtual_o && ((csr_fp_state_access && vsstatus_o[14:13]==0) ||
                       (csr_vector_state_access && vsstatus_o[10:9]==0)))begin
        csr_illegal_o=csr_valid_i;csr_exception_cause_o=2;
      end
    end
    csr_write_effect_o = csr_valid_i && !csr_illegal_o && csr_write_intent;
  end

  always_comb begin
    enabled_interrupts = (mie_q | XLEN'(h_hie)) & mip_value;
    interrupt_global_enable = (current_priv_q != PRIV_M) ||
                              mstatus_q[MSTATUS_MIE];
    enabled_machine_interrupts=enabled_interrupts & ~mideleg_q & {XLEN{interrupt_global_enable}};
    enabled_supervisor_interrupts=enabled_interrupts & mideleg_q & ~XLEN'(h_hideleg) &
      {XLEN{HAS_SMODE && current_priv_q!=PRIV_M && (virtual_o || current_priv_q==PRIV_U || mstatus_q[1])}};
    enabled_vs_interrupts=enabled_interrupts & mideleg_q & XLEN'(h_hideleg) &
      {XLEN{HAS_H && virtual_o && (current_priv_q==PRIV_U || vsstatus_o[1])}};
    interrupt_pending_o = |enabled_machine_interrupts || |enabled_supervisor_interrupts || |enabled_vs_interrupts;
    wfi_wake_o = |enabled_interrupts;
    interrupt_cause_o = 6'd0;
    if(enabled_vs_interrupts[6])interrupt_cause_o=6'd6;
    if(enabled_vs_interrupts[2])interrupt_cause_o=6'd2;
    if(enabled_vs_interrupts[10])interrupt_cause_o=6'd10;
    if(enabled_supervisor_interrupts[13])interrupt_cause_o=6'd13;
    if(enabled_supervisor_interrupts[6])interrupt_cause_o=6'd6;
    if(enabled_supervisor_interrupts[2])interrupt_cause_o=6'd2;
    if(enabled_supervisor_interrupts[10])interrupt_cause_o=6'd10;
    if(enabled_supervisor_interrupts[5]) interrupt_cause_o=6'd5;
    if(enabled_supervisor_interrupts[1]) interrupt_cause_o=6'd1;
    if(enabled_supervisor_interrupts[9]) interrupt_cause_o=6'd9;
    if(enabled_machine_interrupts[13])interrupt_cause_o=6'd13;
    // Supervisor sources can target M when they are not delegated. Their
    // cause numbers are unchanged, and M-targeted sources outrank every
    // HS/VS-targeted source regardless of the current privilege context.
    if(enabled_machine_interrupts[5])interrupt_cause_o=6'd5;
    if(enabled_machine_interrupts[1])interrupt_cause_o=6'd1;
    if(enabled_machine_interrupts[9])interrupt_cause_o=6'd9;
    if (enabled_machine_interrupts[MIP_MTIP])
      interrupt_cause_o = 6'd7;
    if (enabled_machine_interrupts[MIP_MSIP])
      interrupt_cause_o = 6'd3;
    if (enabled_machine_interrupts[MIP_MEIP])
      interrupt_cause_o = 6'd11;

    trap_ready_o = 1'b1;
    trap_vector_o = trap_to_s ? {stvec_q[XLEN-1:2],2'b00}:{mtvec_q[XLEN-1:2], 2'b00};
    if (trap_is_interrupt_i && ((trap_to_s ? stvec_q[1:0]:mtvec_q[1:0]) == 2'b01))
      trap_vector_o = trap_vector_o +
                      (XLEN'(trap_cause_i) << 2);
    if(HAS_H && h_to_vs)trap_vector_o=XLEN'(h_trap_vector);

    mret_ready_o = 1'b1;
    mret_pc_o = {mepc_q[XLEN-1:1], 1'b0};
    mret_illegal_o = mret_valid_i && (current_priv_q != PRIV_M);
    sret_pc_o={sepc_q[XLEN-1:1],1'b0};
    sret_illegal_o=sret_valid_i && (!HAS_SMODE || current_priv_q==PRIV_U ||
      (current_priv_q==PRIV_S && mstatus_q[22]));
    sfence_illegal_o=sfence_valid_i && (!HAS_SMODE || current_priv_q==PRIV_U ||
      (current_priv_q==PRIV_S && mstatus_q[20]));
    // With S-mode present, U-mode WFI must complete or trap in bounded time.
    // Trap immediately; an unbounded U sleep could otherwise prevent the
    // supervisor from regaining control when no interrupt source is enabled.
    wfi_illegal_o = wfi_valid_i &&
                    ((current_priv_q != PRIV_M && mstatus_q[MSTATUS_TW]) ||
                     (HAS_SMODE && current_priv_q == PRIV_U));
    sret_cause_o=2;sfence_cause_o=2;wfi_cause_o=2;
    if(HAS_H && virtual_o)begin
      sret_pc_o=XLEN'(h_return_pc);
      sret_illegal_o=sret_valid_i && (current_priv_q==PRIV_U || hstatus_o[22]);
      sfence_illegal_o=sfence_valid_i && (current_priv_q==PRIV_U || hstatus_o[20]);
      if(sret_illegal_o)sret_cause_o=22;
      if(sfence_illegal_o)sfence_cause_o=22;
      if(wfi_valid_i && !mstatus_q[MSTATUS_TW] && (current_priv_q==PRIV_U || hstatus_o[21]))begin
        wfi_illegal_o=1;wfi_cause_o=22;
      end
    end
  end

  // Scalar trap CSR storage is independent of the unrelated large PMP case
  // write network. No FF/stage/port change. Preserve the exact priority:
  // reset > trap > legal committed MRET (hold) > matching pending CSR write.
  logic trap_state_csr_write;
  assign trap_state_csr_write =
    csr_commit_i && csr_pending_q && csr_pending_write_q;
  assign vector_csr_write_o=HAS_V && trap_state_csr_write &&
    csr_pending_addr_q inside {12'h008,12'h009,12'h00a,12'h00f};
  assign vector_csr_address_o=csr_pending_addr_q;
  assign vector_csr_data_o=64'(csr_pending_wdata_q);
  always_ff @(posedge clk_i) begin
    if (!rst_ni)
      mepc_q <= '0;
    else if (trap_valid_i && trap_ready_o && !trap_to_s)
      mepc_q <= trap_is_interrupt_i ?
        {trap_next_pc_i[XLEN-1:1], 1'b0} : {trap_pc_i[XLEN-1:1], 1'b0};
    else if (mret_valid_i && mret_commit_i && !mret_illegal_o) begin
    end else if (trap_state_csr_write && (csr_pending_addr_q == 12'h341))
      mepc_q <= {csr_pending_wdata_q[XLEN-1:1], 1'b0};
  end
  always_ff @(posedge clk_i) begin
    if (!rst_ni)
      mcause_q <= '0;
    else if (trap_valid_i && trap_ready_o && !trap_to_s)
      mcause_q <= {trap_is_interrupt_i, {(XLEN-7){1'b0}}, trap_cause_i};
    else if (mret_valid_i && mret_commit_i && !mret_illegal_o) begin
    end else if (trap_state_csr_write && (csr_pending_addr_q == 12'h342))
      mcause_q <= csr_pending_wdata_q;
  end
  always_ff @(posedge clk_i) begin
    if (!rst_ni)
      mtval_q <= '0;
    else if (trap_valid_i && trap_ready_o && !trap_to_s)
      mtval_q <= trap_tval_i;
    else if (mret_valid_i && mret_commit_i && !mret_illegal_o) begin
    end else if (trap_state_csr_write && (csr_pending_addr_q == 12'h343))
      mtval_q <= csr_pending_wdata_q;
  end

  // Counters advance even on trap/MRET cycles. Only a pending counter write
  // is blocked by those higher-priority actions. Isolate storage from the
  // unrelated CSR/PMP case network, retaining RV32 partial-write semantics:
  // low-half write holds old high half; high-half write keeps incremented low.
  logic counter_csr_write;
  logic [63:0] mcycle_incremented, minstret_incremented;
  logic mcycle_low_write, mcycle_high_write;
  logic minstret_low_write, minstret_high_write;
  assign counter_csr_write = trap_state_csr_write &&
    !(trap_valid_i && trap_ready_o) &&
    !(mret_valid_i && mret_commit_i && !mret_illegal_o);
  assign mcycle_incremented = increment_counter(mcycle_q, mcountinhibit_q[0] ? 2'd0:2'd1);
  assign minstret_incremented = increment_counter(minstret_q, mcountinhibit_q[2] ? 2'd0:retire_count_i);
  assign mcycle_low_write = counter_csr_write && (csr_pending_addr_q == 12'hB00);
  assign mcycle_high_write = (XLEN == 32) && counter_csr_write &&
    (csr_pending_addr_q == 12'hB80);
  assign minstret_low_write = counter_csr_write && (csr_pending_addr_q == 12'hB02);
  assign minstret_high_write = (XLEN == 32) && counter_csr_write &&
    (csr_pending_addr_q == 12'hB82);
  always_ff @(posedge clk_i) begin
    if (!rst_ni)
      mcycle_q <= '0;
    else begin
      if (XLEN == 32) begin
        mcycle_q[31:0] <= mcycle_low_write ? csr_pending_wdata_q[31:0] :
          mcycle_incremented[31:0];
        mcycle_q[63:32] <= mcycle_low_write ? mcycle_q[63:32] :
          (mcycle_high_write ? csr_pending_wdata_q[31:0] : mcycle_incremented[63:32]);
      end else
        mcycle_q <= mcycle_low_write ? csr_pending_wdata_q : mcycle_incremented;
    end
  end
  always_ff @(posedge clk_i) begin
    if (!rst_ni)
      minstret_q <= '0;
    else begin
      if (XLEN == 32) begin
        minstret_q[31:0] <= minstret_low_write ? csr_pending_wdata_q[31:0] :
          minstret_incremented[31:0];
        minstret_q[63:32] <= minstret_low_write ? minstret_q[63:32] :
          (minstret_high_write ? csr_pending_wdata_q[31:0] : minstret_incremented[63:32]);
      end else
        minstret_q <= minstret_low_write ? csr_pending_wdata_q : minstret_incremented;
    end
  end

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      current_priv_q <= PRIV_M;
      mstatus_q <= '0;
      mie_q <= '0;
      mtvec_q <= {RESET_MTVEC[XLEN-1:2], 2'b00};
      mscratch_q <= '0;
      mcounteren_q <= '0;
      medeleg_q<=0;mideleg_q<=HAS_H?XLEN'('h444):'0;stvec_q<=0;sscratch_q<=0;sepc_q<=0;scause_q<=0;stval_q<=0;scounteren_q<=0;
      software_mip_q<=0;satp_q<=0;menvcfg_q<=0;senvcfg_q<=0;stimecmp_q<=64'hffffffffffffffff;mcountinhibit_q<=0;
      fflags_q <= '0;
      frm_q <= '0;
      csr_pending_q <= 1'b0;
      csr_pending_addr_q <= '0;
      csr_pending_write_q <= 1'b0;
      csr_pending_wdata_q <= '0;
      for (int unsigned entry = 0; entry < PMP_ENTRIES; entry++) begin
        pmpcfg_q[entry] <= '0;
        pmpaddr_q[entry] <= '0;
      end
    end else begin
      if(HAS_F && (fp_state_write_i || (fflags_accrue_valid_i && |fflags_accrue_i)))
        mstatus_q[MSTATUS_FS_LO +: 2]<=2'b11;
      if(HAS_V && (vector_state_write_i || vector_csr_write_o))mstatus_q[10:9]<=3;
      if (fflags_accrue_valid_i)
        fflags_q <= fflags_q | fflags_accrue_i;

      if (flush_all_i)
        csr_pending_q <= 1'b0;
      else if (csr_valid_i && csr_execute_i && !csr_illegal_o) begin
        csr_pending_q <= 1'b1;
        csr_pending_addr_q <= csr_addr_i;
        csr_pending_write_q <= csr_write_intent;
        csr_pending_wdata_q <= csr_write_value;
      end

      if (trap_valid_i && trap_ready_o) begin
        if(HAS_H && h_to_vs)begin
          current_priv_q<=PRIV_S;
        end else if(trap_to_s) begin
          sepc_q<=trap_is_interrupt_i ? {trap_next_pc_i[XLEN-1:1],1'b0}:{trap_pc_i[XLEN-1:1],1'b0};
          scause_q<={trap_is_interrupt_i,{(XLEN-7){1'b0}},trap_cause_i};stval_q<=trap_tval_i;
          mstatus_q[5]<=mstatus_q[1];mstatus_q[1]<=0;mstatus_q[8]<=current_priv_q==PRIV_S;
          current_priv_q<=PRIV_S;
        end else begin
          mstatus_q[MSTATUS_MPIE] <= mstatus_q[MSTATUS_MIE];
          mstatus_q[MSTATUS_MIE] <= 1'b0;
          mstatus_q[MSTATUS_MPP_LO +: 2] <= current_priv_q;
          current_priv_q <= PRIV_M;
        end
      end else if (mret_valid_i && mret_commit_i && !mret_illegal_o) begin
        current_priv_q <= privilege_e'(mstatus_q[MSTATUS_MPP_LO +: 2]);
        mstatus_q[MSTATUS_MIE] <= mstatus_q[MSTATUS_MPIE];
        mstatus_q[MSTATUS_MPIE] <= 1'b1;
        mstatus_q[MSTATUS_MPP_LO +: 2] <= PRIV_U;
        if (mstatus_q[MSTATUS_MPP_LO +: 2] != PRIV_M)
          mstatus_q[MSTATUS_MPRV] <= 1'b0;
      end else if(sret_valid_i && sret_commit_i && !sret_illegal_o) begin
        current_priv_q<=HAS_H?privilege_e'(h_return_privilege):(mstatus_q[8] ? PRIV_S:PRIV_U);
        if(!virtual_o)begin mstatus_q[1]<=mstatus_q[5];mstatus_q[5]<=1;mstatus_q[8]<=0;end
        mstatus_q[17]<=0;
      end else if (csr_commit_i && csr_pending_q) begin
        csr_pending_q <= 1'b0;
        if(csr_pending_write_q && csr_pending_addr_q inside {12'h001,12'h002,12'h003})
          mstatus_q[MSTATUS_FS_LO +: 2]<=2'b11;
        if (csr_pending_write_q && !(HAS_H && h_selected)) case (csr_pending_addr_q)
          12'h001: fflags_q <= csr_pending_wdata_q[4:0];
          12'h002: frm_q <= csr_pending_wdata_q[2:0];
          12'h003: begin
            fflags_q <= csr_pending_wdata_q[4:0];
            frm_q <= csr_pending_wdata_q[7:5];
          end
          12'h300: mstatus_q <= sanitize_mstatus(csr_pending_wdata_q);
          12'h100:mstatus_q<=sanitize_mstatus((mstatus_q & ~sstatus_write_mask) | (csr_pending_wdata_q & sstatus_write_mask));
          12'h104:mie_q<=(mie_q & ~delegated_supervisor_mask) |
                         (csr_pending_wdata_q & delegated_supervisor_mask);
          12'h105:stvec_q<={csr_pending_wdata_q[XLEN-1:2],csr_pending_wdata_q[1:0]==1 ? 2'b01:2'b00};
          12'h106:scounteren_q<=csr_pending_wdata_q & XLEN'(COUNTER_ENABLE_MASK);
          12'h10a:begin
            senvcfg_q<=64'(csr_pending_wdata_q) & (HAS_CBO?64'hf1:64'h1);
            if(HAS_CBO && csr_pending_wdata_q[5:4]==2)
              senvcfg_q[5:4]<=senvcfg_q[5:4];
            // PMM=00/10 implement PMLEN=0/7. Reserved/unsupported writes
            // retain the previous legal PMM while other fields still update.
            if(HAS_SSNPM && XLEN==64)
              senvcfg_q[33:32]<= (64'(csr_pending_wdata_q)>>32 & 3)==0 ? 2'd0:
                ((64'(csr_pending_wdata_q)>>32 & 3)==2 ? 2'd2:senvcfg_q[33:32]);
          end
          12'h140:sscratch_q<=csr_pending_wdata_q;
          12'h141:sepc_q<={csr_pending_wdata_q[XLEN-1:1],1'b0};
          12'h142:scause_q<=csr_pending_wdata_q;
          12'h143:stval_q<=csr_pending_wdata_q;
          12'h144:if(mideleg_q[1]) software_mip_q[1]<=csr_pending_wdata_q[1];
          12'h14d:stimecmp_q<=64'(csr_pending_wdata_q);
          12'h180:if(XLEN==64 && (csr_pending_wdata_q[XLEN-1-:4]==0 || csr_pending_wdata_q[XLEN-1-:4]==8))
            satp_q<=64'(csr_pending_wdata_q);
          12'h302:medeleg_q<=csr_pending_wdata_q & MEDELEG_MASK;
          12'h303:mideleg_q<=(csr_pending_wdata_q & S_INTERRUPT_MASK) | (HAS_H?XLEN'('h444):XLEN'(0));
          12'h30a:begin
            menvcfg_q<=64'(csr_pending_wdata_q) & (HAS_CBO?64'hc0000000000000f1:64'hc000000000000001);
            if(HAS_CBO && csr_pending_wdata_q[5:4]==2)
              menvcfg_q[5:4]<=menvcfg_q[5:4];
          end
          12'h320:mcountinhibit_q<=csr_pending_wdata_q & XLEN'(32'h5|HPM_MASK);
          // LCOFIP has one owner in the HPM bank. Keeping a second software
          // copy would leave it set after a delegated SIP clear.
          12'h344:software_mip_q<=csr_pending_wdata_q & XLEN'('h222);
          12'h304: begin
            mie_q <= csr_pending_wdata_q & (M_INTERRUPT_MASK|
              (HAS_SMODE?S_INTERRUPT_MASK:XLEN'(0))|(HPM_COUNTERS!=0?XLEN'('h2000):XLEN'(0)));
            mie_q[MIP_MSIP] <= csr_pending_wdata_q[MIP_MSIP];
            mie_q[MIP_MTIP] <= csr_pending_wdata_q[MIP_MTIP];
            mie_q[MIP_MEIP] <= csr_pending_wdata_q[MIP_MEIP];
          end
          12'h305: begin
            mtvec_q <= {csr_pending_wdata_q[XLEN-1:2], 2'b00};
            if (csr_pending_wdata_q[1:0] == 2'b01)
              mtvec_q[1:0] <= 2'b01;
          end
          12'h306: mcounteren_q <= csr_pending_wdata_q & XLEN'(COUNTER_ENABLE_MASK);
          12'h340: mscratch_q <= csr_pending_wdata_q;
          12'hB00, 12'hB02, 12'hB80, 12'hB82: begin end
          default: begin
            for (int unsigned cfg_csr = 0; cfg_csr < 4; cfg_csr++) begin
              if (csr_pending_addr_q == (12'h3A0 + cfg_csr)) begin
                for (int unsigned byte_index = 0;
                     byte_index < (XLEN/8); byte_index++) begin
                  int unsigned entry_index;
                  logic [7:0] cfg_value;
                  entry_index = cfg_csr * 4 + byte_index;
                  if (XLEN == 64)
                    entry_index = (cfg_csr / 2) * 8 + byte_index;
                  cfg_value = csr_pending_wdata_q[byte_index*8 +: 8];
                  // Baseline PMP reserves bits 6:5 as read-only zero.
                  // No optional PMP extension consumes them in this core.
                  cfg_value[6:5] = 2'b00;
                  if ((entry_index < PMP_ENTRIES) &&
                      !pmpcfg_q[entry_index][7]) begin
                    // Reserved R=0,W=1 is coerced to no permissions.
                    if (!cfg_value[0] && cfg_value[1])
                      cfg_value[2:0] = 3'b000;
                    pmpcfg_q[entry_index] <= cfg_value;
                  end
                end
              end
            end
            for (int unsigned entry = 0; entry < PMP_ENTRIES; entry++) begin
              if ((csr_pending_addr_q == (12'h3B0 + entry)) &&
                  !pmp_address_locked(entry))
                pmpaddr_q[entry] <= PMP_ADDR_WIDTH'(csr_pending_wdata_q &
                  ((XLEN'(1)<<(IMPLEMENTED_PADDR_WIDTH-2))-XLEN'(1)));
            end
          end
        endcase
      end
    end
  end

  assign privilege_o = current_priv_q;
  assign mstatus_o = mstatus_read_value;
  assign mtvec_o = mtvec_q;
  assign mepc_o = mepc_q;
  assign frm_o = frm_q;
  assign fflags_o = fflags_q;
  assign satp_o=satp_q;assign menvcfg_o=menvcfg_q;assign senvcfg_o=senvcfg_q;
  generate
    for (genvar entry = 0; entry < PMP_ENTRIES; entry++) begin : g_pmp_output
      assign pmpcfg_o[entry] = pmpcfg_q[entry];
      assign pmpaddr_o[entry] = pmpaddr_q[entry];
    end
  endgenerate

`ifndef SYNTHESIS
  property p_no_illegal_csr_write;
    @(posedge clk_i) disable iff (!rst_ni)
      csr_valid_i && csr_commit_i && csr_illegal_o |-> !csr_write_effect_o;
  endproperty
  assert property (p_no_illegal_csr_write);

  property p_trap_enters_machine_mode;
    @(posedge clk_i) disable iff (!rst_ni)
      trap_valid_i && trap_ready_o && !trap_to_s |=> privilege_o == PRIV_M;
  endproperty
  assert property (p_trap_enters_machine_mode);
`endif

  initial begin : p_parameter_checks
    if(HAS_H && (XLEN!=64 || !HAS_SMODE))$fatal(1,"H CSR implementation requires RV64 S mode");
    if ((XLEN != 32) && (XLEN != 64))
      $fatal(1, "CSR file XLEN must be 32 or 64");
    if ((PADDR_WIDTH < 4) || ((PADDR_WIDTH-2) > XLEN))
      $fatal(1, "CSR PMP address width must be in [2, XLEN]");
    if ((PMP_ENTRIES == 0) || (PMP_ENTRIES > 16))
      $fatal(1, "CSR file supports 1..16 PMP entries");
  end

endmodule

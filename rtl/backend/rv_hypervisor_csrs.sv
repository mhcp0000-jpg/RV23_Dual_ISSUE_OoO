// RV64 H/VS architectural CSR and trap-state bank. CSR writes are committed
// writes from an external head owner; ordinary HS/M CSRs remain in rv_csr_file.
// Development component: no misa.H claim until the complete core consumes it.
module rv_hypervisor_csrs #(
  parameter logic [63:0] COUNTER_MASK=64'h7
)(
  input logic clk_i,rst_ni,
  input logic csr_valid_i,csr_commit_write_i,
  input logic csr_write_intent_i=0,
  input logic [11:0] csr_address_i,
  input logic [63:0] csr_write_data_i,
  input logic [1:0] privilege_i,
  input logic [63:0] mstatus_i,menvcfg_i,mcounteren_i,mtime_i,
  output logic csr_selected_o,
  output logic [63:0] csr_data_o,
  output logic csr_exception_o,
  output logic [5:0] csr_cause_o,
  input logic mstatus_commit_write_i=0,mie_commit_write_i=0,mip_commit_write_i=0,
  input logic [63:0] machine_write_data_i=0,
  input logic fp_dirty_i=0,vector_dirty_i=0,
  input logic trap_commit_i=0,trap_delegated_i=0,trap_interrupt_i=0,trap_guest_va_i=0,
  input logic [5:0] trap_cause_i=0,
  input logic [63:0] trap_pc_i=0,trap_next_pc_i=0,trap_tval_i=0,trap_guest_address_i=0,
  input logic trap_implicit_guest_access_i=0,
  output logic trap_to_vs_o,
  output logic [63:0] vs_trap_vector_o,
  input logic mret_commit_i=0,sret_commit_i=0,xret_is_mret_i=0,
  input logic [63:0] hs_return_pc_i=0,m_return_pc_i=0,
  output logic [1:0] xret_privilege_o,
  output logic xret_virtual_o,
  output logic [63:0] xret_pc_o,
  output logic virtual_o,mpv_o,gva_o,
  output logic [63:0] hstatus_o,hedeleg_o,hideleg_o,henvcfg_o,hcounteren_o,
  output logic [63:0] vsstatus_o,vsatp_o,hgatp_o,hip_o,hie_o,htimedelta_o,
  output logic [63:0] mtval2_o,mtinst_o
);
  localparam logic [63:0] V_INTERRUPTS=64'h444;
  localparam logic [63:0] HEDELEG_MASK=64'hb1ff;
  localparam logic [63:0] STATUS_MASK=64'hc6722;
  localparam logic [63:0] HSTATUS_MASK=64'h00030000007003c0;
  logic [63:0] hstatus_q,hedeleg_q,hideleg_q,henvcfg_q,hcounteren_q,htimedelta_q,hgatp_q;
  logic [63:0] htval_q,htinst_q,hvip_q,hie_q;
  logic [63:0] vsstatus_q,vstvec_q,vsscratch_q,vsepc_q,vscause_q,vstval_q,vsatp_q,vstimecmp_q;
  logic [63:0] mtval2_q,mtinst_q;
  logic virtual_q,mpv_q,gva_q;
  logic [11:0] address;
  logic vs_window,direct_vs,hypervisor_window,machine_window;
  logic [5:0] vs_cause;
  logic [63:0] guest_time,vs_interrupts,vs_enable,env_mask;
  logic guest_fault;
  assign virtual_o=virtual_q;assign mpv_o=mpv_q;assign gva_o=gva_q;
  assign hstatus_o=hstatus_q|64'h200000000;
  assign hedeleg_o=hedeleg_q;assign hideleg_o=hideleg_q;
  assign hcounteren_o=hcounteren_q;assign htimedelta_o=htimedelta_q;
  assign henvcfg_o={henvcfg_q[63:62]&menvcfg_i[63:62],henvcfg_q[61:0]};
  assign vsatp_o=vsatp_q;assign hgatp_o=hgatp_q;
  assign hie_o=hie_q;assign guest_time=mtime_i+htimedelta_q;
  assign hip_o=hvip_q | ((henvcfg_o[63] && guest_time>=vstimecmp_q)?64'h40:64'b0);
  assign vs_interrupts=(hip_o&hideleg_q)>>1;
  assign vs_enable=(hie_q&hideleg_q)>>1;
  assign vsstatus_o=vsstatus_q|64'h200000000|
    ((vsstatus_q[14:13]==3 || vsstatus_q[10:9]==3)?64'h8000000000000000:64'b0);
  assign mtval2_o=mtval2_q;assign mtinst_o=mtinst_q;
  assign guest_fault=!trap_interrupt_i && trap_cause_i inside {6'd20,6'd21,6'd23};
  assign trap_to_vs_o=privilege_i!=3 && virtual_q && trap_delegated_i &&
    (trap_interrupt_i?hideleg_q[trap_cause_i]:hedeleg_q[trap_cause_i]);
  assign vs_cause=trap_interrupt_i && trap_cause_i inside {6'd2,6'd6,6'd10}?trap_cause_i-1'b1:trap_cause_i;
  assign vs_trap_vector_o={vstvec_q[63:2],2'b0}+
    ((trap_interrupt_i && vstvec_q[1:0]==1)?(64'(vs_cause)<<2):64'b0);
  always_comb begin
    if(xret_is_mret_i)begin
      xret_privilege_o=mstatus_i[12:11];xret_virtual_o=mstatus_i[12:11]!=3 && mpv_q;xret_pc_o=m_return_pc_i;
    end else begin
      xret_privilege_o=virtual_q?(vsstatus_q[8]?2'd1:2'd0):(mstatus_i[8]?2'd1:2'd0);
      xret_virtual_o=virtual_q || hstatus_q[7];xret_pc_o=virtual_q?vsepc_q:hs_return_pc_i;
    end
  end
  always_comb begin
    address=csr_address_i;
    vs_window=virtual_q && csr_address_i inside {12'h100,12'h104,12'h105,12'h140,12'h141,12'h142,12'h143,12'h144,12'h14d,12'h180};
    if(vs_window)address=csr_address_i+12'h100;
    direct_vs=address inside {12'h200,12'h204,12'h205,12'h240,12'h241,12'h242,12'h243,12'h244,12'h24d,12'h280};
    hypervisor_window=address inside {12'h600,12'h602,12'h603,12'h604,12'h606,12'h607,12'h60a,12'h643,12'h644,12'h645,12'h64a,12'h680,12'he12,12'h605};
    machine_window=address inside {12'h34a,12'h34b};
    csr_selected_o=direct_vs || hypervisor_window || machine_window;
    csr_data_o=0;
    case(address)
      12'h600:csr_data_o=hstatus_o;
      12'h602:csr_data_o=hedeleg_q;
      12'h603:csr_data_o=hideleg_q;
      12'h604:csr_data_o=hie_q;
      12'h605:csr_data_o=htimedelta_q;
      12'h606:csr_data_o=hcounteren_q;
      12'h60a:csr_data_o=henvcfg_o;
      12'h643:csr_data_o=htval_q;
      12'h644:csr_data_o=hip_o;
      12'h645:csr_data_o=hvip_q;
      12'h64a:csr_data_o=htinst_q;
      12'h680:csr_data_o=hgatp_q;
      12'h34a:csr_data_o=mtinst_q;
      12'h34b:csr_data_o=mtval2_q;
      12'h200:csr_data_o=vsstatus_o;
      12'h204:csr_data_o=vs_enable;
      12'h205:csr_data_o=vstvec_q;
      12'h240:csr_data_o=vsscratch_q;
      12'h241:csr_data_o=vsepc_q;
      12'h242:csr_data_o=vscause_q;
      12'h243:csr_data_o=vstval_q;
      12'h244:csr_data_o=vs_interrupts;
      12'h24d:csr_data_o=vstimecmp_q;
      12'h280:csr_data_o=vsatp_q;
      default:begin end // GEILEN=0: hgeie/hgeip and VGEIN are RAZ.
    endcase
    csr_exception_o=0;csr_cause_o=2;
    if(csr_valid_i && csr_selected_o)begin
      if(machine_window)csr_exception_o=privilege_i!=3;
      // Sstc machine gates take precedence even for direct vstimecmp access
      // in a guest. A virtual-instruction trap requires an HS-legal access.
      else if(address==12'h24d && privilege_i!=3 && (!mcounteren_i[1] || !menvcfg_i[63]))csr_exception_o=1;
      else if(virtual_q && !vs_window)begin csr_exception_o=1;csr_cause_o=22;end
      else if(privilege_i==0)begin csr_exception_o=1;csr_cause_o=virtual_q?6'd22:6'd2;end
      else if(address==12'h680 && privilege_i==1 && mstatus_i[20])csr_exception_o=1;
      else if(vs_window && address==12'h280 && hstatus_q[20])begin csr_exception_o=1;csr_cause_o=22;end
      else if(address==12'h24d && vs_window && (!hcounteren_q[1] || !henvcfg_o[63]))begin
        csr_exception_o=1;csr_cause_o=22;
      end
      if(csr_address_i[11:10]==3 && (csr_write_intent_i || csr_commit_write_i))begin csr_exception_o=1;csr_cause_o=2;end
    end
    env_mask=64'h00000003000000f1|{menvcfg_i[63:62],62'b0};
  end
  always_ff @(posedge clk_i)begin
    if(!rst_ni)begin
      hstatus_q<=0;hedeleg_q<=0;hideleg_q<=0;henvcfg_q<=0;hcounteren_q<=0;htimedelta_q<=0;hgatp_q<=0;
      htval_q<=0;htinst_q<=0;hvip_q<=0;hie_q<=0;vsstatus_q<=0;vstvec_q<=0;vsscratch_q<=0;
      vsepc_q<=0;vscause_q<=0;vstval_q<=0;vsatp_q<=0;vstimecmp_q<='1;
      mtval2_q<=0;mtinst_q<=0;virtual_q<=0;mpv_q<=0;gva_q<=0;
    end else begin
      if(virtual_q && fp_dirty_i)vsstatus_q[14:13]<=3;
      if(virtual_q && vector_dirty_i)vsstatus_q[10:9]<=3;
      if(mstatus_commit_write_i)begin mpv_q<=machine_write_data_i[39];gva_q<=machine_write_data_i[38];end
      if(mie_commit_write_i)hie_q<=machine_write_data_i&V_INTERRUPTS;
      if(mip_commit_write_i)hvip_q[2]<=machine_write_data_i[2];
      if(csr_valid_i && csr_commit_write_i && csr_selected_o && !csr_exception_o)case(address)
        12'h600:begin
          hstatus_q<=csr_write_data_i&HSTATUS_MASK;
          if(!(csr_write_data_i[49:48] inside {2'd0,2'd2}))hstatus_q[49:48]<=hstatus_q[49:48];
        end
        12'h602:hedeleg_q<=csr_write_data_i&HEDELEG_MASK;
        12'h603:hideleg_q<=csr_write_data_i&V_INTERRUPTS;
        12'h604:hie_q<=csr_write_data_i&V_INTERRUPTS;
        12'h605:htimedelta_q<=csr_write_data_i;
        12'h606:hcounteren_q<=csr_write_data_i&COUNTER_MASK;
        12'h60a:begin
          henvcfg_q<=csr_write_data_i&env_mask;
          if(csr_write_data_i[5:4]==2)henvcfg_q[5:4]<=henvcfg_q[5:4];
          if(!(csr_write_data_i[33:32] inside {2'd0,2'd2}))henvcfg_q[33:32]<=henvcfg_q[33:32];
        end
        12'h643:htval_q<=csr_write_data_i;
        12'h644:hvip_q[2]<=csr_write_data_i[2];
        12'h645:hvip_q<=csr_write_data_i&V_INTERRUPTS;
        12'h64a:htinst_q<=csr_write_data_i;
        12'h680:begin
          // An unsupported MODE leaves MODE unchanged. The aligned root PPN
          // is still written, and VMID and reserved bits stay read-only zero.
          if(csr_write_data_i[63:60] inside {4'd0,4'd8})
            hgatp_q[63:60]<=csr_write_data_i[63:60];
          hgatp_q[59:0]<={16'b0,csr_write_data_i[43:2],2'b0};
        end
        12'h34a:mtinst_q<=csr_write_data_i;
        12'h34b:mtval2_q<=csr_write_data_i;
        12'h200:vsstatus_q<=csr_write_data_i&STATUS_MASK;
        12'h204:hie_q<=(hie_q&~hideleg_q)|((csr_write_data_i<<1)&hideleg_q&V_INTERRUPTS);
        12'h205:vstvec_q<={csr_write_data_i[63:2],csr_write_data_i[1:0]==1?2'b01:2'b00};
        12'h240:vsscratch_q<=csr_write_data_i;
        12'h241:vsepc_q<={csr_write_data_i[63:1],1'b0};
        12'h242:vscause_q<=csr_write_data_i;
        12'h243:vstval_q<=csr_write_data_i;
        12'h244:if(hideleg_q[2])hvip_q[2]<=csr_write_data_i[1];
        12'h24d:vstimecmp_q<=csr_write_data_i;
        12'h280:if(csr_write_data_i[63:60] inside {4'd0,4'd8})vsatp_q<=csr_write_data_i;
        default:begin end
      endcase
      // Trap and return events override CSR state writes on the same edge.
      if(trap_commit_i)begin
        if(trap_to_vs_o)begin
          vsstatus_q[5]<=vsstatus_q[1];vsstatus_q[1]<=0;vsstatus_q[8]<=privilege_i==1;
          vsepc_q<={(trap_interrupt_i?trap_next_pc_i[63:1]:trap_pc_i[63:1]),1'b0};
          vscause_q<={trap_interrupt_i,57'b0,vs_cause};vstval_q<=trap_tval_i;
        end else begin
          virtual_q<=0;
          if(trap_delegated_i && privilege_i!=3)begin
            hstatus_q[7]<=virtual_q;hstatus_q[6]<=trap_guest_va_i;
            if(virtual_q)hstatus_q[8]<=privilege_i==1;
            htval_q<=guest_fault?(trap_guest_address_i>>2):64'b0;
            htinst_q<=guest_fault && trap_implicit_guest_access_i?64'h3000:64'b0;
          end else begin
            mpv_q<=virtual_q;gva_q<=trap_guest_va_i;
            mtval2_q<=guest_fault?(trap_guest_address_i>>2):64'b0;
            mtinst_q<=guest_fault && trap_implicit_guest_access_i?64'h3000:64'b0;
          end
        end
      end else if(mret_commit_i)begin virtual_q<=mstatus_i[12:11]!=3 && mpv_q;mpv_q<=0;end
      else if(sret_commit_i)begin
        if(virtual_q)begin vsstatus_q[1]<=vsstatus_q[5];vsstatus_q[5]<=1;vsstatus_q[8]<=0;end
        else begin virtual_q<=hstatus_q[7];hstatus_q[7]<=0;end
      end
    end
  end
endmodule

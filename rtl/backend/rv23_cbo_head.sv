// Write-through cache management and 64-byte CBO.ZERO at the architectural head.
// Caller drains older memory before acceptance. Translation and block-wide PMP
// checks precede every side effect. Management reads permissions without D;
// zero checks write permission and D. Fault tval is the original transformed rs1.
module rv23_cbo_head #(
  parameter int unsigned XLEN=64,ADDRESS_WIDTH=64,
  parameter bit HAS_MMU=1,HAS_SSNPM=1
)(
  input logic clk_i,rst_ni,invalidate_i,
  input logic request_valid_i,
  output logic request_ready_o,
  input logic [XLEN-1:0] address_i,
  input logic [11:0] operation_i,
  input logic [31:0] instruction_i,
  input rv_ooo_pkg::privilege_e privilege_i,effective_privilege_i,
  input logic [XLEN-1:0] mstatus_i,
  input logic [63:0] satp_i,menvcfg_i,senvcfg_i,
  input logic virtual_i=0,guest_instruction_i=0,hs_mxr_i=0,guest_pbmt_enable_i=0,
  input logic [63:0] vsatp_i=0,hgatp_i=0,henvcfg_i=0,
  input logic [1:0] pmm_i=0,
  input logic [7:0][7:0] pmpcfg_i,
  input logic [7:0][ADDRESS_WIDTH-3:0] pmpaddr_i,
  output logic response_valid_o,
  input logic response_ready_i,
  output logic response_exception_o,
  output logic [5:0] response_cause_o,
  output logic [XLEN-1:0] response_tval_o,
  output logic [63:0] response_guest_address_o,
  output logic response_implicit_guest_access_o,
  output logic cache_invalidate_valid_o,
  input logic cache_invalidate_ready_i,
  output logic ptw_valid_o,ptw_device_o,
  input logic ptw_ready_i,
  output logic [55:0] ptw_address_o,
  input logic ptw_response_valid_i,
  output logic ptw_response_ready_o,
  input logic [63:0] ptw_data_i,
  input logic ptw_error_i,
  output logic write_valid_o,
  output logic write_device_o,
  input logic write_ready_i,
  output logic [31:0] write_address_o,
  input logic write_response_valid_i,
  output logic write_response_ready_o,
  input logic write_response_error_i
);
  import rv_ooo_pkg::*;
  typedef enum logic[3:0] {IDLE,TRANSLATE,WAIT_TRANSLATE,CHECK,INVALIDATE,
                          WRITE_ADDR,WRITE_RESPONSE,RESULT} state_t;
  state_t state_q;
  logic [63:0] masked,va_q;
  logic [31:0] pa_q;
  logic [11:0] operation_q;
  logic [2:0] word_q;
  privilege_e effective_privilege_q;
  logic exception_q,permission;
  logic machine_permission,guest_permission,supervisor_permission,device_q,implicit_q,trans_implicit;
  logic [63:0] guest_q,trans_guest;
  logic [5:0] permission_cause;
  logic [5:0] cause_q;
  logic [0:0][ADDRESS_WIDTH-1:0] pmp_address;
  logic [0:0][2:0] pmp_size,pmp_access;
  privilege_e [0:0] pmp_privilege;
  logic [0:0] pmp_read_allow,pmp_write_allow;
  logic trans_ready,trans_valid,trans_fault;
  logic [31:0] trans_address;
  logic [5:0] trans_cause;
  logic [1:0] trans_pbmt;
  rv23_pointer_mask #(.ENABLE(HAS_SSNPM && XLEN==64)) u_mask(
    .address_i(64'(address_i)),.privilege_i(virtual_i?2'd0:effective_privilege_i),.pmm_i(virtual_i?pmm_i:senvcfg_i[33:32]),
    .translated_i(virtual_i?vsatp_i[63:60]!=0:satp_i[63:60]!=0),.mxr_i(mstatus_i[19] || (virtual_i && hs_mxr_i)),.address_o(masked));
  always_comb begin
    machine_permission=1;guest_permission=1;supervisor_permission=1;permission_cause=2;
    if(privilege_i!=PRIV_M) case(operation_i)
      0:begin machine_permission=menvcfg_i[5:4]!=0;guest_permission=henvcfg_i[5:4]!=0;supervisor_permission=privilege_i!=PRIV_U || senvcfg_i[5:4]!=0;end
      1,2:begin machine_permission=menvcfg_i[6];guest_permission=henvcfg_i[6];supervisor_permission=privilege_i!=PRIV_U || senvcfg_i[6];end
      4:begin machine_permission=menvcfg_i[7];guest_permission=henvcfg_i[7];supervisor_permission=privilege_i!=PRIV_U || senvcfg_i[7];end
      default:begin machine_permission=0;guest_permission=0;supervisor_permission=0;end
    endcase
    permission=machine_permission && supervisor_permission && (!guest_instruction_i || guest_permission);
    if(guest_instruction_i && machine_permission && (!guest_permission || !supervisor_permission))permission_cause=22;
  end
  assign request_ready_o=state_q==IDLE;
  assign response_valid_o=state_q==RESULT;
  assign response_exception_o=exception_q;assign response_cause_o=cause_q;
  assign response_tval_o=XLEN'(va_q);
  assign response_guest_address_o=guest_q;assign response_implicit_guest_access_o=implicit_q;
  assign cache_invalidate_valid_o=state_q==INVALIDATE;
  assign pmp_address[0]=ADDRESS_WIDTH'({pa_q[31:6],6'b0});
  assign pmp_size[0]=6;assign pmp_access[0]=3'b001;
  assign pmp_privilege[0]=effective_privilege_q;
  rv_pmp #(.PADDR_WIDTH(ADDRESS_WIDTH),.CHECK_PORTS(1)) u_read_pmp(
    .pmpcfg_i,.pmpaddr_i,.check_valid_i(1'b1),.check_address_i(pmp_address),
    .check_size_i(pmp_size),.check_access_i(pmp_access),.check_privilege_i(pmp_privilege),
    .allow_o(pmp_read_allow),.matched_o(),.fault_address_o());
  rv_pmp #(.PADDR_WIDTH(ADDRESS_WIDTH),.CHECK_PORTS(1)) u_write_pmp(
    .pmpcfg_i,.pmpaddr_i,.check_valid_i(1'b1),.check_address_i(pmp_address),
    .check_size_i(pmp_size),.check_access_i(3'b010),.check_privilege_i(pmp_privilege),
    .allow_o(pmp_write_allow),.matched_o(),.fault_address_o());
  if(HAS_MMU) begin:g_translation
    rv23_translation_port u_translate(.clk_i,.rst_ni,.invalidate_i,
      .req_valid_i(state_q==TRANSLATE),.req_ready_o(trans_ready),.req_address_i(va_q),
      .req_access_i(operation_q==4?2'd2:2'd1),.req_privilege_i(effective_privilege_q),
      .req_virtual_i(virtual_i),.req_sum_i(mstatus_i[18]),.req_mxr_i(mstatus_i[19]),
      .req_hs_mxr_i(hs_mxr_i),.req_pbmt_enable_i(menvcfg_i[62]),.req_guest_pbmt_enable_i(guest_pbmt_enable_i),
      .satp_i,.vsatp_i,.hgatp_i,.rsp_valid_o(trans_valid),
      .rsp_ready_i(state_q==WAIT_TRANSLATE),.rsp_address_o(trans_address),.rsp_pbmt_o(trans_pbmt),
      .rsp_fault_o(trans_fault),.rsp_cause_o(trans_cause),.rsp_tval_o(),
      .rsp_guest_address_o(trans_guest),.rsp_implicit_guest_access_o(trans_implicit),
      .mem_valid_o(ptw_valid_o),.mem_device_o(ptw_device_o),.mem_ready_i(ptw_ready_i),
      .mem_address_o(ptw_address_o),.mem_response_valid_i(ptw_response_valid_i),
      .mem_response_ready_o(ptw_response_ready_o),.mem_response_data_i(ptw_data_i),.mem_response_error_i(ptw_error_i));
  end else begin:g_bare
    assign trans_ready=1;assign trans_valid=1;assign trans_address=va_q[31:0];
    assign trans_pbmt=0;assign trans_fault=va_q[63:32]!=0;assign trans_cause=7;
    assign trans_guest=0;assign trans_implicit=0;
    assign ptw_valid_o=0;assign ptw_device_o=0;assign ptw_address_o=0;assign ptw_response_ready_o=0;
  end
  assign write_valid_o=state_q==WRITE_ADDR;
  assign write_device_o=device_q;
  assign write_address_o={pa_q[31:6],word_q,3'b0};
  assign write_response_ready_o=state_q==WRITE_RESPONSE;
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      state_q<=IDLE;va_q<=0;pa_q<=0;operation_q<=0;word_q<=0;
      effective_privilege_q<=PRIV_M;exception_q<=0;cause_q<=0;
      guest_q<=0;implicit_q<=0;device_q<=0;
    end else case(state_q)
      IDLE:if(request_valid_i) begin
        va_q<=masked;operation_q<=operation_i;effective_privilege_q<=effective_privilege_i;
        exception_q<=0;cause_q<=0;word_q<=0;
        guest_q<=0;implicit_q<=0;device_q<=0;
        if(!permission || !(operation_i==0 || operation_i==1 || operation_i==2 || operation_i==4)) begin
          exception_q<=1;cause_q<=permission_cause;va_q<=64'(instruction_i);
          state_q<=RESULT;
        end else state_q<=TRANSLATE;
      end
      TRANSLATE:if(trans_ready) state_q<=WAIT_TRANSLATE;
      WAIT_TRANSLATE:if(trans_valid) begin
        pa_q<=trans_address;
        device_q<=trans_pbmt!=0;
        if(trans_fault) begin
          exception_q<=1;
          guest_q<=trans_guest;implicit_q<=trans_implicit;
          case(trans_cause)
            13:cause_q<=15;21:cause_q<=23;5:cause_q<=7;default:cause_q<=trans_cause;
          endcase
          state_q<=RESULT;
        end else state_q<=CHECK;
      end
      CHECK:begin
        if((operation_q==4 ? !pmp_write_allow[0]:!(pmp_read_allow[0] || pmp_write_allow[0])) ||
            (operation_q==4 ? (pa_q<32'h80000000 || pa_q>=32'h80100000):
             rv23_pkg::decode_target(pa_q)==rv_soc_pkg::SOC_TARGET_ERROR)) begin
          exception_q<=1;cause_q<=7;state_q<=RESULT;
        end else if(operation_q==4) state_q<=WRITE_ADDR;
        // All lines are clean once older write-through responses have drained.
        else if(operation_q==1) state_q<=RESULT;
        else state_q<=INVALIDATE;
      end
      INVALIDATE:if(cache_invalidate_ready_i) state_q<=RESULT;
      WRITE_ADDR:if(write_ready_i) state_q<=WRITE_RESPONSE;
      WRITE_RESPONSE:if(write_response_valid_i) begin
        if(write_response_error_i) begin exception_q<=1;cause_q<=7;state_q<=RESULT;end
        else if(word_q==7) state_q<=RESULT;
        else begin word_q<=word_q+1'b1;state_q<=WRITE_ADDR;end
      end
      RESULT:if(response_ready_i) state_q<=IDLE;
      default:state_q<=IDLE;
    endcase
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    write_valid_o && !write_ready_i |=> write_valid_o && $stable(write_address_o));
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    response_valid_o && !response_ready_i |=> response_valid_o &&
      $stable({response_exception_o,response_cause_o,response_tval_o}));
`endif
endmodule

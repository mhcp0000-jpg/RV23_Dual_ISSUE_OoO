// Serialized ROB-head address validation. No atomic side effect is requested
// until translation, PMP read/write authority and main-memory PMA all pass.
module rv23_atomic_head #(
  parameter int unsigned XLEN=64,
  parameter bit HAS_SSNPM=0,
  parameter int unsigned ADDRESS_WIDTH=64,
  parameter bit HAS_MMU=1
)(
  input logic clk_i,rst_ni,invalidate_i,
  input logic request_valid_i,
  output logic request_ready_o,
  input logic [XLEN-1:0] address_i,operand_i,
  input logic [31:0] instruction_i,
  input rv_ooo_pkg::privilege_e privilege_i,
  input logic [XLEN-1:0] mstatus_i,
  input logic [63:0] satp_i,menvcfg_i,senvcfg_i,
  input logic virtual_i=0,hs_mxr_i=0,guest_pbmt_enable_i=0,
  input logic [63:0] vsatp_i=0,hgatp_i=0,
  input logic [1:0] pmm_i=0,
  input logic [7:0][7:0] pmpcfg_i,
  input logic [7:0][ADDRESS_WIDTH-3:0] pmpaddr_i,
  output logic response_valid_o,
  input logic response_ready_i,
  output logic [XLEN-1:0] response_data_o,response_tval_o,
  output logic response_exception_o,
  output logic [5:0] response_cause_o,
  output logic [63:0] response_guest_address_o,
  output logic response_implicit_guest_access_o,
  output logic engine_valid_o,
  input logic engine_ready_i,
  output logic [31:0] engine_address_o,
  output logic [63:0] engine_operand_o,
  output logic [4:0] engine_operation_o,
  output logic engine_word_o,engine_privileged_o,
  input logic engine_response_valid_i,
  output logic engine_response_ready_o,
  input logic [63:0] engine_data_i,
  input logic engine_exception_i,
  input logic [5:0] engine_cause_i,
  output logic ptw_valid_o,ptw_device_o,
  input logic ptw_ready_i,
  output logic [55:0] ptw_address_o,
  input logic ptw_response_valid_i,
  output logic ptw_response_ready_o,
  input logic [63:0] ptw_data_i,
  input logic ptw_error_i
);
  import rv_ooo_pkg::*;
  typedef enum logic[2:0] {IDLE,TRANSLATE,WAIT_TRANSLATE,CHECK,SEND,WAIT_ENGINE,RESULT} state_t;
  state_t state_q;
  logic [63:0] va_q,operand_q,masked_address;
  logic [63:0] guest_q,translation_guest;
  logic implicit_q,translation_implicit;
  rv23_pointer_mask #(.ENABLE(HAS_SSNPM && XLEN==64)) u_pointer_mask (
    .address_i(64'(address_i)),.privilege_i(virtual_i?2'd0:privilege_i),.pmm_i(virtual_i?pmm_i:senvcfg_i[33:32]),
    .translated_i(virtual_i?vsatp_i[63:60]!=0:satp_i[63:60]!=0),.mxr_i(mstatus_i[19] || (virtual_i && hs_mxr_i)),.address_o(masked_address));
  logic [31:0] pa_q;
  logic [4:0] operation_q;
  logic word_q,exception_q;
  logic [5:0] cause_q;
  logic [XLEN-1:0] result_q;
  privilege_e privilege_q;
  logic translation_ready,translation_valid,translation_fault;
  logic [31:0] translated;
  logic [5:0] translation_cause;
  logic [1:0] pbmt;
  logic [0:0] pmp_allow;
  logic [0:0][ADDRESS_WIDTH-1:0] pmp_address;
  logic [0:0][2:0] pmp_size,pmp_access;
  privilege_e [0:0] pmp_privilege;
  assign request_ready_o=state_q==IDLE;
  assign response_valid_o=state_q==RESULT;
  assign response_data_o=result_q;assign response_tval_o=XLEN'(va_q);
  assign response_exception_o=exception_q;assign response_cause_o=cause_q;
  assign response_guest_address_o=guest_q;assign response_implicit_guest_access_o=implicit_q;
  assign engine_valid_o=state_q==SEND;
  assign engine_address_o=pa_q;assign engine_operand_o=operand_q;
  assign engine_operation_o=operation_q;assign engine_word_o=word_q;
  assign engine_privileged_o=privilege_q!=PRIV_U;
  assign engine_response_ready_o=state_q==WAIT_ENGINE;
  assign pmp_address[0]=ADDRESS_WIDTH'(pa_q);
  assign pmp_size[0]=word_q?2:3;
  assign pmp_access[0]=operation_q==2 ? 3'b001:(operation_q==3?3'b010:3'b011);
  assign pmp_privilege[0]=privilege_q;
  rv_pmp #(.PADDR_WIDTH(ADDRESS_WIDTH),.CHECK_PORTS(1)) u_pmp(
    .pmpcfg_i,.pmpaddr_i,.check_valid_i(1'b1),.check_address_i(pmp_address),
    .check_size_i(pmp_size),.check_access_i(pmp_access),.check_privilege_i(pmp_privilege),
    .allow_o(pmp_allow),.matched_o(),.fault_address_o());
  if(HAS_MMU) begin:g_mmu
    rv23_translation_port u_translate(.clk_i,.rst_ni,.invalidate_i,
      .req_valid_i(state_q==TRANSLATE),.req_ready_o(translation_ready),
      .req_address_i(va_q),.req_access_i(operation_q==2?2'd1:2'd2),
      .req_privilege_i(privilege_q),.req_virtual_i(virtual_i),
      .req_sum_i(mstatus_i[18]),.req_mxr_i(mstatus_i[19]),.req_hs_mxr_i(hs_mxr_i),
      .req_pbmt_enable_i(menvcfg_i[62]),.req_guest_pbmt_enable_i(guest_pbmt_enable_i),
      .satp_i,.vsatp_i,.hgatp_i,
      .rsp_valid_o(translation_valid),.rsp_ready_i(state_q==WAIT_TRANSLATE),
      .rsp_address_o(translated),.rsp_pbmt_o(pbmt),.rsp_fault_o(translation_fault),
      .rsp_cause_o(translation_cause),.rsp_tval_o(),.rsp_guest_address_o(translation_guest),
      .rsp_implicit_guest_access_o(translation_implicit),.mem_valid_o(ptw_valid_o),.mem_device_o(ptw_device_o),
      .mem_ready_i(ptw_ready_i),.mem_address_o(ptw_address_o),
      .mem_response_valid_i(ptw_response_valid_i),.mem_response_ready_o(ptw_response_ready_o),
      .mem_response_data_i(ptw_data_i),.mem_response_error_i(ptw_error_i));
  end else begin:g_bare
    assign translation_ready=1;assign translation_valid=1;
    assign translated=va_q[31:0];assign pbmt=0;
    assign translation_fault=va_q[63:32]!=0;
    assign translation_cause=operation_q==2?6'd5:6'd7;
    assign translation_guest=0;assign translation_implicit=0;
    assign ptw_valid_o=0;assign ptw_device_o=0;assign ptw_address_o=0;assign ptw_response_ready_o=0;
  end
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      state_q<=IDLE;va_q<=0;operand_q<=0;pa_q<=0;operation_q<=0;word_q<=0;
      exception_q<=0;cause_q<=0;result_q<=0;privilege_q<=PRIV_M;
      guest_q<=0;implicit_q<=0;
    end else case(state_q)
      IDLE:if(request_valid_i) begin
        va_q<=masked_address;operand_q<=64'(operand_i);operation_q<=instruction_i[31:27];
        word_q<=instruction_i[14:12]==2;privilege_q<=privilege_i;
        exception_q<=0;cause_q<=0;result_q<=0;
        guest_q<=0;implicit_q<=0;
        if((address_i & (instruction_i[14:12]==2?XLEN'(3):XLEN'(7)))!=0) begin
          exception_q<=1;cause_q<=instruction_i[31:27]==2?6'd4:6'd6;state_q<=RESULT;
        end else state_q<=TRANSLATE;
      end
      TRANSLATE:if(translation_ready) state_q<=WAIT_TRANSLATE;
      WAIT_TRANSLATE:if(translation_valid) begin
        pa_q<=translated;
        if(translation_fault) begin
          exception_q<=1;cause_q<=translation_cause;state_q<=RESULT;
          guest_q<=translation_guest;implicit_q<=translation_implicit;
        end
        // PBMT=IO is not an atomic-capable memory PMA. NC SRAM remains atomic.
        else if(pbmt==2) begin exception_q<=1;cause_q<=operation_q==2?6'd5:6'd7;state_q<=RESULT;end
        else state_q<=CHECK;
      end
      CHECK:begin
        if(!pmp_allow[0] || pa_q<32'h80000000 || pa_q>=32'h80100000) begin
          exception_q<=1;cause_q<=operation_q==2?6'd5:6'd7;state_q<=RESULT;
        end else state_q<=SEND;
      end
      SEND:if(engine_ready_i) state_q<=WAIT_ENGINE;
      WAIT_ENGINE:if(engine_response_valid_i) begin
        result_q<=XLEN'(engine_data_i);exception_q<=engine_exception_i;cause_q<=engine_cause_i;state_q<=RESULT;
      end
      RESULT:if(response_ready_i) state_q<=IDLE;
      default:state_q<=IDLE;
    endcase
  end
endmodule

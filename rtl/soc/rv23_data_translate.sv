// Translate AGU updates BEFORE LSU validation and store commit. A page fault
// therefore becomes a precise ROB exception, never a failed committed store.
module rv23_data_translate #(
  parameter int unsigned PAYLOAD_WIDTH=1,
  parameter int unsigned PADDR_WIDTH=32,
  parameter int unsigned SEQ_WIDTH=8
)(
  input logic clk_i,rst_ni,invalidate_i,
  input logic valid_i,
  output logic ready_o,
  input logic [PAYLOAD_WIDTH-1:0] payload_i,
  input logic [63:0] address_i,
  input logic [SEQ_WIDTH-1:0] sequence_i,
  input logic translate_i,store_i,
  input logic flush_i,flush_all_i,
  input logic [SEQ_WIDTH-1:0] flush_sequence_i,
  input logic [1:0] privilege_i,
  input logic virtual_i,sum_i,mxr_i,hs_mxr_i,pbmt_enable_i,guest_pbmt_enable_i,
  input logic [63:0] satp_i,vsatp_i,hgatp_i,
  output logic valid_o,
  input logic ready_i,
  output logic [PAYLOAD_WIDTH-1:0] payload_o,
  output logic [PADDR_WIDTH-1:0] address_o,
  output logic fault_o,
  output logic [5:0] cause_o,
  output logic [63:0] tval_o,guest_address_o,
  output logic implicit_guest_access_o,
  output logic [1:0] pbmt_o,
  output logic idle_o,
  output logic mem_valid_o,
  output logic mem_device_o,
  input logic mem_ready_i,
  output logic [55:0] mem_address_o,
  input logic mem_response_valid_i,
  output logic mem_response_ready_o,
  input logic [63:0] mem_response_data_i,
  input logic mem_response_error_i
);
  typedef enum logic [1:0] {IDLE,WAIT_TRANSLATION,NO_TRANSLATION} state_e;
  state_e state_q;
  logic [PAYLOAD_WIDTH-1:0] payload_q;
  logic [63:0] address_q;
  logic [SEQ_WIDTH-1:0] sequence_q;
  logic killed_q,kill;
  logic trans_ready,trans_valid,trans_rsp_ready;
  logic [PADDR_WIDTH-1:0] trans_address;
  logic trans_fault,trans_implicit;
  logic [5:0] trans_cause;
  logic [63:0] trans_tval,trans_gpa;
  logic [1:0] trans_pbmt;
  function automatic logic younger(input logic [SEQ_WIDTH-1:0] a,b);
    logic signed [SEQ_WIDTH-1:0] delta;
    delta=$signed(a-b);return delta>0;
  endfunction
  assign kill=flush_i && (flush_all_i || younger(sequence_q,flush_sequence_i));
  assign ready_o=rst_ni && !flush_i && state_q==IDLE && (!translate_i || trans_ready);
  assign idle_o=state_q==IDLE;
  assign payload_o=payload_q;
  assign valid_o=rst_ni && !killed_q && !kill &&
    (state_q==NO_TRANSLATION || (state_q==WAIT_TRANSLATION && trans_valid));
  assign address_o=state_q==NO_TRANSLATION ? PADDR_WIDTH'(address_q):trans_address;
  assign fault_o=state_q==WAIT_TRANSLATION && trans_fault;
  assign cause_o=trans_cause;assign tval_o=trans_tval;assign guest_address_o=trans_gpa;
  assign implicit_guest_access_o=trans_implicit;assign pbmt_o=trans_pbmt;
  assign trans_rsp_ready=state_q==WAIT_TRANSLATION && (killed_q || kill || ready_i);
  rv23_translation_port #(.PADDR_WIDTH(PADDR_WIDTH)) u_tlb (
    .clk_i,.rst_ni,.invalidate_i,.req_valid_i(valid_i && ready_o && translate_i),.req_ready_o(trans_ready),
    .req_address_i(address_i),.req_access_i(store_i ? 2'd2:2'd1),.req_privilege_i(privilege_i),
    .req_virtual_i(virtual_i),.req_sum_i(sum_i),.req_mxr_i(mxr_i),.req_hs_mxr_i(hs_mxr_i),
    .req_pbmt_enable_i(pbmt_enable_i),.req_guest_pbmt_enable_i(guest_pbmt_enable_i),
    .satp_i,.vsatp_i,.hgatp_i,.rsp_valid_o(trans_valid),.rsp_ready_i(trans_rsp_ready),
    .rsp_address_o(trans_address),.rsp_pbmt_o(trans_pbmt),.rsp_fault_o(trans_fault),.rsp_cause_o(trans_cause),
    .rsp_tval_o(trans_tval),.rsp_guest_address_o(trans_gpa),.rsp_implicit_guest_access_o(trans_implicit),
    .mem_valid_o,.mem_device_o,.mem_ready_i,.mem_address_o,.mem_response_valid_i,.mem_response_ready_o,
    .mem_response_data_i,.mem_response_error_i);
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin state_q<=IDLE;payload_q<=0;address_q<=0;sequence_q<=0;killed_q<=0;end
    else begin
      if(kill) killed_q<=1;
      case(state_q)
        IDLE:if(valid_i && ready_o) begin
          payload_q<=payload_i;address_q<=address_i;sequence_q<=sequence_i;killed_q<=0;
          state_q<=translate_i ? WAIT_TRANSLATION:NO_TRANSLATION;
        end
        NO_TRANSLATION:if(killed_q || kill || ready_i) state_q<=IDLE;
        WAIT_TRANSLATION:if(trans_valid && trans_rsp_ready) state_q<=IDLE;
        default:state_q<=IDLE;
      endcase
    end
  end
endmodule

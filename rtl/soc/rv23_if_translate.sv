module rv23_if_translate #(
  parameter int unsigned PADDR_WIDTH=32,
  parameter int unsigned FETCH_BYTES=16
)(
  input logic clk_i,rst_ni,invalidate_i,halt_i,
  input logic req_valid_i,
  output logic req_ready_o,
  input logic [63:0] req_address_i,
  input logic [3:0] req_id_i,req_epoch_i,
  input logic [1:0] privilege_i,
  input logic virtual_i,mxr_i,hs_mxr_i,pbmt_enable_i,guest_pbmt_enable_i,
  input logic [63:0] satp_i,vsatp_i,hgatp_i,
  output logic rsp_valid_o,
  input logic rsp_ready_i,
  output logic [3:0] rsp_id_o,rsp_epoch_o,
  output logic [FETCH_BYTES*8-1:0] rsp_data_o,
  output logic [1:0] rsp_resp_o,
  output logic [5:0] rsp_cause_o,
  output logic [63:0] rsp_guest_address_o,
  output logic rsp_implicit_guest_access_o,
  output logic [PADDR_WIDTH-1:0] physical_address_o,
  output logic idle_o,
  output logic bus_valid_o,
  input logic bus_ready_i,
  output logic [PADDR_WIDTH-1:0] bus_address_o,
  output logic [3:0] bus_id_o,bus_epoch_o,
  output logic bus_device_o,
  input logic bus_rsp_valid_i,
  input logic [3:0] bus_rsp_id_i=0,bus_rsp_epoch_i=0,
  output logic bus_rsp_ready_o,
  input logic [FETCH_BYTES*8-1:0] bus_rsp_data_i,
  input logic [1:0] bus_rsp_resp_i,
  output logic mem_valid_o,
  output logic mem_device_o,
  input logic mem_ready_i,
  output logic [55:0] mem_address_o,
  input logic mem_response_valid_i,
  output logic mem_response_ready_o,
  input logic [63:0] mem_response_data_i,
  input logic mem_response_error_i
);
  typedef enum logic [2:0] {IDLE,TRANSLATE,ISSUE,WAIT_DATA,FAULT} state_e;
  state_e state_q;
  logic [3:0] id_q,epoch_q;
  logic [PADDR_WIDTH-1:0] pa_q,trans_pa;
  logic [5:0] cause_q,trans_cause;
  logic [63:0] guest_q,trans_guest,trans_tval;
  logic implicit_q,trans_implicit,trans_fault,trans_ready,trans_rsp_valid,device_q;
  logic [1:0] trans_pbmt;
  assign req_ready_o=rst_ni && !halt_i && state_q==IDLE && trans_ready;
  assign idle_o=state_q==IDLE;
  assign physical_address_o=pa_q;
  assign rsp_valid_o=rst_ni && (state_q==FAULT || (state_q==WAIT_DATA && bus_rsp_valid_i));
  assign rsp_id_o=state_q==FAULT?id_q:bus_rsp_id_i;
  assign rsp_epoch_o=state_q==FAULT?epoch_q:bus_rsp_epoch_i;
  assign rsp_data_o=state_q==FAULT ? '0:bus_rsp_data_i;
  assign rsp_resp_o=state_q==FAULT ? 2'b10:bus_rsp_resp_i;
  assign rsp_cause_o=state_q==FAULT ? cause_q:6'd1;
  assign rsp_guest_address_o=guest_q;assign rsp_implicit_guest_access_o=implicit_q;
  assign bus_valid_o=rst_ni && state_q==ISSUE;
  assign bus_address_o=pa_q;assign bus_id_o=id_q;assign bus_epoch_o=epoch_q;assign bus_device_o=device_q;
  assign bus_rsp_ready_o=state_q==WAIT_DATA && rsp_ready_i;
  rv23_translation_port #(.PADDR_WIDTH(PADDR_WIDTH)) u_tlb (
    .clk_i,.rst_ni,.invalidate_i,.req_valid_i(req_valid_i && req_ready_o),.req_ready_o(trans_ready),
    .req_address_i,.req_access_i(2'd0),.req_privilege_i(privilege_i),.req_virtual_i(virtual_i),
    .req_sum_i(1'b0),.req_mxr_i(mxr_i),.req_hs_mxr_i(hs_mxr_i),.req_pbmt_enable_i(pbmt_enable_i),
    .req_guest_pbmt_enable_i(guest_pbmt_enable_i),.satp_i,.vsatp_i,.hgatp_i,
    .rsp_valid_o(trans_rsp_valid),.rsp_ready_i(state_q==TRANSLATE),.rsp_address_o(trans_pa),
    .rsp_pbmt_o(trans_pbmt),.rsp_fault_o(trans_fault),.rsp_cause_o(trans_cause),.rsp_tval_o(trans_tval),
    .rsp_guest_address_o(trans_guest),.rsp_implicit_guest_access_o(trans_implicit),
    .mem_valid_o,.mem_device_o,.mem_ready_i,.mem_address_o,.mem_response_valid_i,.mem_response_ready_o,
    .mem_response_data_i,.mem_response_error_i);
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      state_q<=IDLE;id_q<=0;epoch_q<=0;pa_q<=0;cause_q<=0;guest_q<=0;implicit_q<=0;device_q<=0;
    end else case(state_q)
      IDLE:if(req_valid_i && req_ready_o) begin id_q<=req_id_i;epoch_q<=req_epoch_i;state_q<=TRANSLATE;end
      TRANSLATE:if(trans_rsp_valid) begin
        pa_q<=trans_pa;cause_q<=trans_cause;guest_q<=trans_guest;implicit_q<=trans_implicit;device_q<=trans_pbmt!=0;
        state_q<=trans_fault ? FAULT:ISSUE;
      end
      ISSUE:if(bus_ready_i) state_q<=WAIT_DATA;
      WAIT_DATA:if(bus_rsp_valid_i && rsp_ready_i) state_q<=IDLE;
      FAULT:if(rsp_ready_i) state_q<=IDLE;
      default:state_q<=IDLE;
    endcase
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    bus_valid_o && !bus_ready_i |=> bus_valid_o && $stable({bus_address_o,bus_id_o,bus_epoch_o,bus_device_o}));
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    rsp_valid_o && !rsp_ready_i |=> rsp_valid_o && $stable({rsp_id_o,rsp_epoch_o,rsp_data_o,rsp_resp_o,rsp_cause_o}));
`endif
endmodule

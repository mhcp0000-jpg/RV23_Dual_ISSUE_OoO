// Main-memory misalignment assist. The caller owns the architectural head,
// drains older transactions, and prevents cancellation after acceptance.
// Every byte is translated and checked before the first physical access.
// Byte transfers deliberately avoid assumptions about physical adjacency at
// virtual page, PMP, cache-line and bank boundaries. No atomicity is promised.
module rv23_misaligned_head #(
  parameter int unsigned ADDRESS_WIDTH=64,
  parameter bit HAS_MMU=1,HAS_SSNPM=1
)(
  input logic clk_i,rst_ni,invalidate_i,
  input logic request_valid_i,
  output logic request_ready_o,
  input logic [63:0] address_i,operand_i,
  input logic [2:0] size_i,
  input logic write_i,unsigned_i,floating_i,
  input rv_ooo_pkg::privilege_e privilege_i,
  input logic [63:0] mstatus_i,satp_i,menvcfg_i,senvcfg_i,
  input logic [7:0][7:0] pmpcfg_i,
  input logic [7:0][ADDRESS_WIDTH-3:0] pmpaddr_i,
  output logic response_valid_o,
  input logic response_ready_i,
  output logic [63:0] response_data_o,response_tval_o,
  output logic response_exception_o,
  output logic [5:0] response_cause_o,
  output logic ptw_valid_o,ptw_device_o,
  input logic ptw_ready_i,
  output logic [55:0] ptw_address_o,
  input logic ptw_response_valid_i,
  output logic ptw_response_ready_o,
  input logic [63:0] ptw_data_i,
  input logic ptw_error_i,
  output logic memory_valid_o,
  input logic memory_ready_i,
  output logic memory_write_o,
  output logic [31:0] memory_address_o,
  output logic [63:0] memory_data_o,
  output logic [7:0] memory_strobe_o,
  input logic memory_response_valid_i,
  output logic memory_response_ready_o,
  input logic [63:0] memory_response_data_i,
  input logic memory_response_error_i
);
  import rv_ooo_pkg::*;
  typedef enum logic[2:0] {IDLE,TRANSLATE,WAIT_TRANSLATE,CHECK,
                          MEMORY_REQUEST,MEMORY_RESPONSE,RESULT} state_t;
  state_t state_q;
  logic [63:0] masked,base_q,operand_q,result_q,fault_address_q,byte_va;
  logic [31:0] physical_q[8],translated_q;
  logic [2:0] index_q,size_q,last_byte;
  logic write_q,unsigned_q,floating_q,exception_q;
  privilege_e privilege_q;
  logic [5:0] cause_q;
  logic trans_ready,trans_valid,trans_fault,pmp_allow;
  logic [31:0] trans_address;
  logic [1:0] trans_pbmt;
  logic [5:0] trans_cause;
  logic [0:0][ADDRESS_WIDTH-1:0] pmp_address;
  logic [0:0][2:0] pmp_access;
  privilege_e [0:0] pmp_privilege;
  rv23_pointer_mask #(.ENABLE(HAS_SSNPM)) u_mask(
    .address_i,.privilege_i,.pmm_i(senvcfg_i[33:32]),
    .translated_i(satp_i[63:60]!=0),.mxr_i(mstatus_i[19]),.address_o(masked));
  assign byte_va=base_q+64'(index_q);
  assign last_byte=3'((1<<size_q)-1);
  assign pmp_address[0]=ADDRESS_WIDTH'(translated_q);
  assign pmp_access[0]=write_q?3'b010:3'b001;
  assign pmp_privilege[0]=privilege_q;
  rv_pmp #(.PADDR_WIDTH(ADDRESS_WIDTH),.CHECK_PORTS(1)) u_pmp(
    .pmpcfg_i,.pmpaddr_i,.check_valid_i(1'b1),.check_address_i(pmp_address),
    .check_size_i(3'b0),.check_access_i(pmp_access),.check_privilege_i(pmp_privilege),
    .allow_o(pmp_allow),.matched_o(),.fault_address_o());
  if(HAS_MMU) begin:g_translation
    rv23_translation_port u_translate(.clk_i,.rst_ni,.invalidate_i,
      .req_valid_i(state_q==TRANSLATE),.req_ready_o(trans_ready),.req_address_i(byte_va),
      .req_access_i(write_q?2'd2:2'd1),.req_privilege_i(privilege_q),
      .req_virtual_i(1'b0),.req_sum_i(mstatus_i[18]),.req_mxr_i(mstatus_i[19]),
      .req_hs_mxr_i(1'b0),.req_pbmt_enable_i(menvcfg_i[62]),.req_guest_pbmt_enable_i(1'b0),
      .satp_i,.vsatp_i(64'b0),.hgatp_i(64'b0),.rsp_valid_o(trans_valid),
      .rsp_ready_i(state_q==WAIT_TRANSLATE),.rsp_address_o(trans_address),.rsp_pbmt_o(trans_pbmt),
      .rsp_fault_o(trans_fault),.rsp_cause_o(trans_cause),.rsp_tval_o(),
      .rsp_guest_address_o(),.rsp_implicit_guest_access_o(),
      .mem_valid_o(ptw_valid_o),.mem_device_o(ptw_device_o),.mem_ready_i(ptw_ready_i),
      .mem_address_o(ptw_address_o),.mem_response_valid_i(ptw_response_valid_i),
      .mem_response_ready_o(ptw_response_ready_o),.mem_response_data_i(ptw_data_i),.mem_response_error_i(ptw_error_i));
  end else begin:g_bare
    assign trans_ready=1;assign trans_valid=1;assign trans_address=byte_va[31:0];
    assign trans_pbmt=0;assign trans_fault=byte_va[63:32]!=0;
    assign trans_cause=write_q?6'd7:6'd5;
    assign ptw_valid_o=0;assign ptw_device_o=0;assign ptw_address_o=0;assign ptw_response_ready_o=0;
  end
  assign request_ready_o=state_q==IDLE;
  assign response_valid_o=state_q==RESULT;
  assign response_exception_o=exception_q;assign response_cause_o=cause_q;
  assign response_tval_o=fault_address_q;
  always_comb begin
    response_data_o=result_q;
    if(!write_q) case(size_q)
      0:response_data_o=unsigned_q?{56'b0,result_q[7:0]}:{{56{result_q[7]}},result_q[7:0]};
      1:response_data_o=floating_q?{48'hffffffffffff,result_q[15:0]}:
          (unsigned_q?{48'b0,result_q[15:0]}:{{48{result_q[15]}},result_q[15:0]});
      2:response_data_o=floating_q?{32'hffffffff,result_q[31:0]}:
          (unsigned_q?{32'b0,result_q[31:0]}:{{32{result_q[31]}},result_q[31:0]});
      default:begin end
    endcase
  end
  assign memory_valid_o=state_q==MEMORY_REQUEST;
  assign memory_write_o=write_q;
  assign memory_address_o=physical_q[index_q];
  assign memory_strobe_o=8'b1<<memory_address_o[2:0];
  assign memory_data_o=64'(operand_q[index_q*8+:8])<<(memory_address_o[2:0]*8);
  assign memory_response_ready_o=state_q==MEMORY_RESPONSE;
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      state_q<=IDLE;base_q<=0;operand_q<=0;result_q<=0;fault_address_q<=0;
      index_q<=0;size_q<=0;write_q<=0;unsigned_q<=0;floating_q<=0;
      privilege_q<=PRIV_M;exception_q<=0;cause_q<=0;translated_q<=0;
    end else case(state_q)
      IDLE:if(request_valid_i) begin
        base_q<=masked;operand_q<=operand_i;size_q<=size_i;index_q<=0;
        write_q<=write_i;unsigned_q<=unsigned_i;floating_q<=floating_i;
        privilege_q<=privilege_i;exception_q<=0;cause_q<=0;result_q<=0;
        fault_address_q<=masked;state_q<=TRANSLATE;
        if(size_i>3) begin exception_q<=1;cause_q<=write_i?6'd7:6'd5;state_q<=RESULT;end
      end
      TRANSLATE:if(trans_ready) state_q<=WAIT_TRANSLATE;
      WAIT_TRANSLATE:if(trans_valid) begin
        translated_q<=trans_address;state_q<=CHECK;
        if(trans_fault || trans_pbmt==2) begin
          exception_q<=1;cause_q<=trans_fault?trans_cause:(write_q?6'd7:6'd5);
          fault_address_q<=byte_va;state_q<=RESULT;
        end
      end
      CHECK:begin
        if(!pmp_allow || translated_q<32'h80000000 || translated_q>=32'h80100000) begin
          exception_q<=1;cause_q<=write_q?6'd7:6'd5;fault_address_q<=byte_va;state_q<=RESULT;
        end else begin
          physical_q[index_q]<=translated_q;
          if(index_q==last_byte) begin index_q<=0;state_q<=MEMORY_REQUEST;end
          else begin index_q<=index_q+1'b1;state_q<=TRANSLATE;end
        end
      end
      MEMORY_REQUEST:if(memory_ready_i) state_q<=MEMORY_RESPONSE;
      MEMORY_RESPONSE:if(memory_response_valid_i) begin
        if(memory_response_error_i) begin
          exception_q<=1;cause_q<=write_q?6'd7:6'd5;fault_address_q<=byte_va;state_q<=RESULT;
        end else begin
          if(!write_q) result_q[index_q*8+:8]<=8'(memory_response_data_i>>(physical_q[index_q][2:0]*8));
          if(index_q==last_byte) state_q<=RESULT;
          else begin index_q<=index_q+1'b1;state_q<=MEMORY_REQUEST;end
        end
      end
      RESULT:if(response_ready_i) state_q<=IDLE;
      default:state_q<=IDLE;
    endcase
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    memory_valid_o && !memory_ready_i |=> memory_valid_o &&
      $stable({memory_write_o,memory_address_o,memory_data_o,memory_strobe_o}));
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    response_valid_o && !response_ready_i |=> response_valid_o &&
      $stable({response_data_o,response_exception_o,response_cause_o,response_tval_o}));
`endif
endmodule

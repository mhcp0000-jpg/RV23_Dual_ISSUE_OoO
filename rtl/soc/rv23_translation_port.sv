// Small fully associative, context-qualified 4 KiB translation cache. Each
// entry stores an already checked access class; a read hit never grants write
// permission. Larger leaves may be cached as individual 4 KiB translations.
module rv23_translation_port #(
  parameter int unsigned PADDR_WIDTH=32,
  parameter int unsigned ENTRIES=16,
  localparam int INDEX_W=$clog2(ENTRIES)
)(
  input logic clk_i,rst_ni,invalidate_i,
  input logic req_valid_i,
  output logic req_ready_o,
  input logic [63:0] req_address_i,
  input logic [1:0] req_access_i,req_privilege_i,
  input logic req_virtual_i,req_sum_i,req_mxr_i,req_hs_mxr_i,req_pbmt_enable_i,req_guest_pbmt_enable_i,
  input logic [63:0] satp_i,vsatp_i,hgatp_i,
  output logic rsp_valid_o,
  input logic rsp_ready_i,
  output logic [PADDR_WIDTH-1:0] rsp_address_o,
  output logic [1:0] rsp_pbmt_o,
  output logic rsp_fault_o,
  output logic [5:0] rsp_cause_o,
  output logic [63:0] rsp_tval_o,rsp_guest_address_o,
  output logic rsp_implicit_guest_access_o,
  output logic mem_valid_o,
  output logic mem_device_o,
  input logic mem_ready_i,
  output logic [55:0] mem_address_o,
  input logic mem_response_valid_i,
  output logic mem_response_ready_o,
  input logic [63:0] mem_response_data_i,
  input logic mem_response_error_i
);
  localparam int KEY_WIDTH=202;
  typedef enum logic [1:0] {IDLE,START,WALK,RESPONSE} state_e;
  state_e state_q;
  logic [ENTRIES-1:0] valid_q;
  logic [51:0] tags[ENTRIES];
  logic [KEY_WIDTH-1:0] contexts[ENTRIES];
  logic [PADDR_WIDTH-13:0] ppn[ENTRIES];
  logic [1:0] types[ENTRIES];
  logic [INDEX_W-1:0] victim_q,hit_index;
  logic hit,walk_invalidated_q;
  logic [KEY_WIDTH-1:0] key,key_q;
  logic [63:0] address_q;
  logic [PADDR_WIDTH-1:0] pa_q;
  logic [1:0] pbmt_q;
  logic fault_q,implicit_q;
  logic [5:0] cause_q;
  logic [63:0] guest_address_q;
  logic start_ready,walk_rsp_valid;
  logic [PADDR_WIDTH-1:0] walk_pa;
  logic [1:0] walk_pbmt;
  logic walk_fault,walk_implicit;
  logic [5:0] walk_cause;
  logic [63:0] walk_tval,walk_guest_address;
  assign key={satp_i,vsatp_i,hgatp_i,req_privilege_i,req_access_i,req_virtual_i,
    req_sum_i,req_mxr_i,req_hs_mxr_i,req_pbmt_enable_i,req_guest_pbmt_enable_i};
  assign req_ready_o=rst_ni && state_q==IDLE;
  assign rsp_valid_o=rst_ni && state_q==RESPONSE;
  assign rsp_address_o=pa_q;assign rsp_pbmt_o=pbmt_q;assign rsp_fault_o=fault_q;
  assign rsp_cause_o=cause_q;assign rsp_tval_o=address_q;
  assign rsp_guest_address_o=guest_address_q;assign rsp_implicit_guest_access_o=implicit_q;
  always_comb begin
    hit=0;hit_index=0;
    for(int i=0;i<ENTRIES;i++) if(valid_q[i] && !invalidate_i && tags[i]==req_address_i[63:12] && contexts[i]==key) begin
      hit=1;hit_index=INDEX_W'(i);
    end
  end
  rv23_mmu #(.PADDR_WIDTH(PADDR_WIDTH)) u_walk (
    .clk_i,.rst_ni,.req_valid_i(state_q==START),.req_ready_o(start_ready),
    .req_address_i(address_q),.satp_i(key_q[201:138]),.vsatp_i(key_q[137:74]),.hgatp_i(key_q[73:10]),
    .req_privilege_i(key_q[9:8]),.req_access_i(key_q[7:6]),.req_virtual_i(key_q[5]),
    .req_sum_i(key_q[4]),.req_mxr_i(key_q[3]),.req_hs_mxr_i(key_q[2]),
    .req_pbmt_enable_i(key_q[1]),.req_guest_pbmt_enable_i(key_q[0]),
    .rsp_valid_o(walk_rsp_valid),.rsp_ready_i(state_q==WALK),.rsp_address_o(walk_pa),.rsp_pbmt_o(walk_pbmt),
    .rsp_fault_o(walk_fault),.rsp_cause_o(walk_cause),.rsp_tval_o(walk_tval),
    .rsp_guest_address_o(walk_guest_address),.rsp_implicit_guest_access_o(walk_implicit),
    .mem_valid_o,.mem_device_o,.mem_ready_i,.mem_address_o,.mem_response_valid_i,.mem_response_ready_o,
    .mem_response_data_i,.mem_response_error_i);
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      state_q<=IDLE;valid_q<=0;victim_q<=0;walk_invalidated_q<=0;key_q<=0;address_q<=0;
      pa_q<=0;pbmt_q<=0;fault_q<=0;cause_q<=0;guest_address_q<=0;implicit_q<=0;
    end else begin
      if(invalidate_i && state_q!=IDLE) walk_invalidated_q<=1;
      case(state_q)
        IDLE:if(req_valid_i) begin
          address_q<=req_address_i;key_q<=key;walk_invalidated_q<=invalidate_i;
          fault_q<=0;cause_q<=0;pbmt_q<=0;implicit_q<=0;guest_address_q<=0;
          if(!req_virtual_i && (req_privilege_i==3 || satp_i[63:60]==0)) begin
            pa_q<=PADDR_WIDTH'(req_address_i);state_q<=RESPONSE;
            if((req_address_i>>PADDR_WIDTH)!=0) begin
              fault_q<=1;cause_q<=req_access_i==0 ? 6'd1:(req_access_i!=2 ? 6'd5:6'd7);
            end
          end else if(hit) begin
            pa_q<={ppn[hit_index],req_address_i[11:0]};pbmt_q<=types[hit_index];state_q<=RESPONSE;
          end else state_q<=START;
        end
        START:if(start_ready) state_q<=WALK;
        WALK:if(walk_rsp_valid) begin
          pa_q<=walk_pa;pbmt_q<=walk_pbmt;fault_q<=walk_fault;cause_q<=walk_cause;
          guest_address_q<=walk_guest_address;implicit_q<=walk_implicit;state_q<=RESPONSE;
          if(!walk_fault && !walk_invalidated_q && !invalidate_i) begin
            tags[victim_q]<=address_q[63:12];contexts[victim_q]<=key_q;
            ppn[victim_q]<=walk_pa[PADDR_WIDTH-1:12];types[victim_q]<=walk_pbmt;valid_q[victim_q]<=1;
            victim_q<=victim_q==ENTRIES-1 ? '0:victim_q+1'b1;
          end
        end
        RESPONSE:if(rsp_ready_i) state_q<=IDLE;
        default:state_q<=IDLE;
      endcase
      if(invalidate_i) valid_q<=0;
    end
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    rsp_valid_o && !rsp_ready_i |=> rsp_valid_o &&
      $stable({rsp_address_o,rsp_pbmt_o,rsp_fault_o,rsp_cause_o,rsp_tval_o,rsp_guest_address_o,rsp_implicit_guest_access_o}));
`endif
  initial if(ENTRIES<2 || PADDR_WIDTH<32 || PADDR_WIDTH>56) $fatal(1,"Invalid TLB geometry");
endmodule

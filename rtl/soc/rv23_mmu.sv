// Sv39 + Sv39x4 two-stage translation controller. VS PTE reads themselves
// pass through G-stage translation. All physical PTE reads use the same
// ordered memory interface; no translation result is installed speculatively.
module rv23_mmu #(
  parameter int unsigned PADDR_WIDTH=32
)(
  input logic clk_i,rst_ni,
  input logic req_valid_i,
  output logic req_ready_o,
  input logic [63:0] req_address_i,
  input logic [1:0] req_access_i,req_privilege_i,
  input logic req_virtual_i,req_sum_i,req_mxr_i,req_hs_mxr_i,
  input logic req_pbmt_enable_i,req_guest_pbmt_enable_i,
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
  typedef enum logic [3:0] {
    IDLE,START_VS,WALK_VS,START_G_PTE,G_PTE,VS_PTE_REQUEST,VS_PTE_RESPONSE,
    VS_PTE_FAIL_REQUEST,VS_PTE_FAIL_RESPONSE,START_G_FINAL,G_FINAL,RESPONSE
  } state_e;
  state_e state_q;
  logic [63:0] va_q,satp_q,hgatp_q,gpa_q,root_q;
  logic [55:0] pte_pa_q;
  logic [1:0] access_q,privilege_q,pbmt_q,vs_pbmt_q;
  logic virtual_q,sum_q,mxr_q,hs_mxr_q,pbmt_enable_q,guest_pbmt_enable_q;
  logic [PADDR_WIDTH-1:0] pa_q;
  logic fault_q,implicit_q,g_pte_fault_q;
  logic [5:0] cause_q;
  logic vs_start_ready,vs_rsp_valid,vs_rsp_ready,vs_fault,vs_access_fault;
  logic [55:0] vs_pa,vs_mem_address;
  logic [1:0] vs_pbmt;
  logic vs_mem_valid,vs_mem_ready,vs_mem_rsp_valid,vs_mem_rsp_ready,vs_mem_error;
  logic g_start_ready,g_rsp_valid,g_rsp_ready,g_fault,g_access_fault;
  logic [55:0] g_pa,g_mem_address;
  logic [1:0] g_pbmt;
  logic g_mem_valid,g_mem_ready,g_mem_rsp_valid,g_mem_rsp_ready;
  logic g_for_pte,pte_device_q;
  assign g_for_pte=state_q==START_G_PTE || state_q==G_PTE;
  function automatic logic [5:0] fault_cause(input logic [1:0] access_kind,input bit access_fault,input bit guest);
    if(access_fault) return access_kind==0 ? 6'd1:(access_kind!=2 ? 6'd5:6'd7);
    if(guest) return access_kind==0 ? 6'd20:(access_kind!=2 ? 6'd21:6'd23);
    return access_kind==0 ? 6'd12:(access_kind!=2 ? 6'd13:6'd15);
  endfunction
  assign req_ready_o=rst_ni && state_q==IDLE;
  assign rsp_valid_o=rst_ni && state_q==RESPONSE;
  assign rsp_address_o=pa_q;assign rsp_pbmt_o=pbmt_q;
  assign rsp_fault_o=fault_q;assign rsp_cause_o=cause_q;
  assign rsp_tval_o=va_q;assign rsp_guest_address_o=gpa_q;
  assign rsp_implicit_guest_access_o=implicit_q;
  rv23_page_walker #(.PADDR_WIDTH(56)) u_vs (
    .clk_i,.rst_ni,.req_valid_i(state_q==START_VS),.req_ready_o(vs_start_ready),
    .req_address_i(va_q),.req_root_ppn_i(root_q[43:0]),.req_bare_i(root_q[63:60]==0),
    .req_gstage_i(1'b0),.req_access_i(access_q),.req_privilege_i(privilege_q),
    .req_sum_i(sum_q),.req_mxr_i(mxr_q || (virtual_q && hs_mxr_q)),.req_pbmt_enable_i(virtual_q ? guest_pbmt_enable_q:pbmt_enable_q),
    .rsp_valid_o(vs_rsp_valid),.rsp_ready_i(vs_rsp_ready),.rsp_address_o(vs_pa),.rsp_pbmt_o(vs_pbmt),
    .rsp_fault_o(vs_fault),.rsp_access_fault_o(vs_access_fault),.rsp_leaf_level_o(),.rsp_napot_o(),
    .mem_valid_o(vs_mem_valid),.mem_ready_i(vs_mem_ready),.mem_address_o(vs_mem_address),
    .mem_response_valid_i(vs_mem_rsp_valid),.mem_response_ready_o(vs_mem_rsp_ready),
    .mem_response_data_i(mem_response_data_i),.mem_response_error_i(vs_mem_error));
  rv23_page_walker #(.PADDR_WIDTH(PADDR_WIDTH)) u_g (
    .clk_i,.rst_ni,.req_valid_i(state_q==START_G_PTE || state_q==START_G_FINAL),.req_ready_o(g_start_ready),
    .req_address_i(gpa_q),.req_root_ppn_i(hgatp_q[43:0]),.req_bare_i(hgatp_q[63:60]==0),
    .req_gstage_i(1'b1),.req_access_i(g_for_pte ? 2'd1:access_q),.req_privilege_i(2'b00),
    .req_sum_i(1'b0),.req_mxr_i(hs_mxr_q),.req_pbmt_enable_i(pbmt_enable_q),
    .rsp_valid_o(g_rsp_valid),.rsp_ready_i(g_rsp_ready),.rsp_address_o(g_pa),.rsp_pbmt_o(g_pbmt),
    .rsp_fault_o(g_fault),.rsp_access_fault_o(g_access_fault),.rsp_leaf_level_o(),.rsp_napot_o(),
    .mem_valid_o(g_mem_valid),.mem_ready_i(g_mem_ready),.mem_address_o(g_mem_address),
    .mem_response_valid_i(g_mem_rsp_valid),.mem_response_ready_o(g_mem_rsp_ready),
    .mem_response_data_i(mem_response_data_i),.mem_response_error_i(mem_response_error_i));
  always_comb begin
    mem_valid_o=0;mem_device_o=0;mem_address_o=0;mem_response_ready_o=0;
    vs_mem_ready=0;vs_mem_rsp_valid=0;vs_mem_error=mem_response_error_i;
    vs_rsp_ready=state_q==WALK_VS;
    g_mem_ready=0;g_mem_rsp_valid=0;g_rsp_ready=state_q==G_PTE || state_q==G_FINAL;
    if(state_q==G_PTE || state_q==G_FINAL) begin
      mem_valid_o=g_mem_valid;mem_address_o=g_mem_address;g_mem_ready=mem_ready_i;
      g_mem_rsp_valid=mem_response_valid_i;mem_response_ready_o=g_mem_rsp_ready;
    end else if(state_q==WALK_VS && !virtual_q) begin
      mem_valid_o=vs_mem_valid;mem_address_o=vs_mem_address;vs_mem_ready=mem_ready_i;
      vs_mem_rsp_valid=mem_response_valid_i;mem_response_ready_o=vs_mem_rsp_ready;
    end else if(state_q==VS_PTE_REQUEST) begin
      mem_valid_o=vs_mem_valid;mem_device_o=pte_device_q;mem_address_o=pte_pa_q;vs_mem_ready=mem_ready_i;
    end else if(state_q==VS_PTE_RESPONSE) begin
      vs_mem_rsp_valid=mem_response_valid_i;mem_response_ready_o=vs_mem_rsp_ready;
    end else if(state_q==VS_PTE_FAIL_REQUEST) vs_mem_ready=1;
    else if(state_q==VS_PTE_FAIL_RESPONSE) begin vs_mem_rsp_valid=1;vs_mem_error=1;end
  end
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      state_q<=IDLE;va_q<=0;satp_q<=0;hgatp_q<=0;gpa_q<=0;root_q<=0;pte_pa_q<=0;
      access_q<=0;privilege_q<=0;pbmt_q<=0;vs_pbmt_q<=0;virtual_q<=0;sum_q<=0;mxr_q<=0;
      hs_mxr_q<=0;pbmt_enable_q<=0;guest_pbmt_enable_q<=0;pa_q<=0;fault_q<=0;implicit_q<=0;
      g_pte_fault_q<=0;cause_q<=0;pte_device_q<=0;
    end else case(state_q)
      IDLE:if(req_valid_i) begin
        va_q<=req_address_i;access_q<=req_access_i;privilege_q<=req_privilege_i;
        virtual_q<=req_virtual_i;sum_q<=req_sum_i;mxr_q<=req_mxr_i;hs_mxr_q<=req_hs_mxr_i;
        pbmt_enable_q<=req_pbmt_enable_i;guest_pbmt_enable_q<=req_guest_pbmt_enable_i;
        satp_q<=satp_i;root_q<=req_virtual_i ? vsatp_i:satp_i;hgatp_q<=hgatp_i;
        fault_q<=0;implicit_q<=0;g_pte_fault_q<=0;cause_q<=0;pte_device_q<=0;pbmt_q<=0;vs_pbmt_q<=0;gpa_q<=0;pa_q<=0;
        if(!req_virtual_i && (req_privilege_i==3 || satp_i[63:60]==0)) begin
          pa_q<=PADDR_WIDTH'(req_address_i);state_q<=RESPONSE;
          if((req_address_i>>PADDR_WIDTH)!=0) begin fault_q<=1;cause_q<=fault_cause(req_access_i,1,0);end
        end else if((req_virtual_i && vsatp_i[63:60]!=0 && vsatp_i[63:60]!=8) ||
                    (!req_virtual_i && satp_i[63:60]!=8)) begin
          fault_q<=1;cause_q<=fault_cause(req_access_i,0,0);state_q<=RESPONSE;
        end else if(req_virtual_i && hgatp_i[63:60]!=0 && hgatp_i[63:60]!=8) begin
          fault_q<=1;cause_q<=fault_cause(req_access_i,0,1);gpa_q<=req_address_i;state_q<=RESPONSE;
        end else if(req_virtual_i && vsatp_i[63:60]==0) begin
          gpa_q<=req_address_i;state_q<=START_G_FINAL;
        end else state_q<=START_VS;
      end
      START_VS:if(vs_start_ready) state_q<=WALK_VS;
      WALK_VS:begin
        if(vs_rsp_valid) begin
          if(g_pte_fault_q) state_q<=RESPONSE;
          else if(vs_fault) begin
            fault_q<=1;cause_q<=fault_cause(access_q,vs_access_fault,0);state_q<=RESPONSE;
          end else if(virtual_q) begin
            gpa_q<={8'b0,vs_pa};vs_pbmt_q<=vs_pbmt;state_q<=START_G_FINAL;
          end else begin
            pa_q<=PADDR_WIDTH'(vs_pa);pbmt_q<=vs_pbmt;state_q<=RESPONSE;
            if((vs_pa>>PADDR_WIDTH)!=0) begin fault_q<=1;cause_q<=fault_cause(access_q,1,0);end
          end
        end else if(virtual_q && vs_mem_valid) begin
          gpa_q<={8'b0,vs_mem_address};state_q<=START_G_PTE;
        end
      end
      START_G_PTE:if(g_start_ready) state_q<=G_PTE;
      G_PTE:if(g_rsp_valid) begin
        if(g_fault) begin
          fault_q<=1;cause_q<=fault_cause(access_q,g_access_fault,1);
          implicit_q<=1;g_pte_fault_q<=1;state_q<=VS_PTE_FAIL_REQUEST;
        end else begin pte_pa_q<=g_pa;pte_device_q<=g_pbmt!=0;state_q<=VS_PTE_REQUEST;end
      end
      VS_PTE_REQUEST:if(vs_mem_valid && mem_ready_i) state_q<=VS_PTE_RESPONSE;
      VS_PTE_RESPONSE:if(mem_response_valid_i && vs_mem_rsp_ready) state_q<=WALK_VS;
      VS_PTE_FAIL_REQUEST:if(vs_mem_valid) state_q<=VS_PTE_FAIL_RESPONSE;
      VS_PTE_FAIL_RESPONSE:if(vs_mem_rsp_ready) state_q<=WALK_VS;
      START_G_FINAL:if(g_start_ready) state_q<=G_FINAL;
      G_FINAL:if(g_rsp_valid) begin
        fault_q<=g_fault;cause_q<=g_fault ? fault_cause(access_q,g_access_fault,1):0;
        pa_q<=PADDR_WIDTH'(g_pa);
        // G-stage supplies the intermediate attributes; VS-stage may override them.
        pbmt_q<=vs_pbmt_q!=0 ? vs_pbmt_q:g_pbmt;
        state_q<=RESPONSE;
      end
      RESPONSE:if(rsp_ready_i) state_q<=IDLE;
      default:state_q<=IDLE;
    endcase
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    mem_valid_o && !mem_ready_i |=> mem_valid_o && $stable(mem_address_o));
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    rsp_valid_o && !rsp_ready_i |=> rsp_valid_o &&
      $stable({rsp_address_o,rsp_pbmt_o,rsp_fault_o,rsp_cause_o,rsp_tval_o,rsp_guest_address_o,rsp_implicit_guest_access_o}));
`endif
endmodule

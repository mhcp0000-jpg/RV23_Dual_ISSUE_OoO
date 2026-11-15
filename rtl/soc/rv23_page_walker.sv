// Sv39 / Sv39x4 read-only PTW. Svade deliberately faults on clear A/D bits;
// it never silently writes page tables. The two-stage MMU may translate this
// module's implicit PTE reads through another instance for VS-stage walks.
module rv23_page_walker #(
  parameter int unsigned PADDR_WIDTH=32
)(
  input logic clk_i,rst_ni,
  input logic req_valid_i,
  output logic req_ready_o,
  input logic [63:0] req_address_i,
  input logic [43:0] req_root_ppn_i,
  input logic req_bare_i,req_gstage_i,
  input logic [1:0] req_access_i, // 0=fetch, 1=load, 2=store, 3=HLVX load using X
  input logic [1:0] req_privilege_i,
  input logic req_sum_i,req_mxr_i,req_pbmt_enable_i,
  output logic rsp_valid_o,
  input logic rsp_ready_i,
  output logic [55:0] rsp_address_o,
  output logic [1:0] rsp_pbmt_o,
  output logic rsp_fault_o,rsp_access_fault_o,
  output logic [1:0] rsp_leaf_level_o,
  output logic rsp_napot_o,
  output logic mem_valid_o,
  input logic mem_ready_i,
  output logic [55:0] mem_address_o,
  input logic mem_response_valid_i,
  output logic mem_response_ready_o,
  input logic [63:0] mem_response_data_i,
  input logic mem_response_error_i
);
  typedef enum logic [1:0] {IDLE,REQUEST,WAIT_PTE,RESPONSE} state_e;
  state_e state_q;
  logic [63:0] address_q;
  logic [55:0] table_q,result_q;
  logic [1:0] level_q,access_q,privilege_q,pbmt_q,leaf_level_q;
  logic gstage_q,sum_q,mxr_q,pbmt_enable_q,fault_q,access_fault_q,napot_q;
  logic [10:0] vpn;
  logic [63:0] pte;
  logic leaf,pte_invalid,permission,superpage_aligned;
  logic [55:0] leaf_address;
  assign req_ready_o=rst_ni && state_q==IDLE;
  assign rsp_valid_o=rst_ni && state_q==RESPONSE;
  assign rsp_address_o=result_q;assign rsp_pbmt_o=pbmt_q;
  assign rsp_fault_o=fault_q;assign rsp_access_fault_o=access_fault_q;
  assign rsp_leaf_level_o=leaf_level_q;assign rsp_napot_o=napot_q;
  assign mem_valid_o=rst_ni && state_q==REQUEST;
  assign mem_address_o=table_q+(56'(vpn)<<3);
  assign mem_response_ready_o=state_q==WAIT_PTE;
  assign pte=mem_response_data_i;
  always_comb begin
    case(level_q)
      2:vpn=gstage_q ? address_q[40:30]:{2'b0,address_q[38:30]};
      1:vpn={2'b0,address_q[29:21]};
      default:vpn={2'b0,address_q[20:12]};
    endcase
    leaf=pte[1] || pte[3];
    pte_invalid=!pte[0] || (!pte[1] && pte[2]) || (|pte[60:54]) || pte[62:61]==3 ||
      ((!pbmt_enable_q) && (|pte[62:61]));
    if(!leaf) pte_invalid|=pte[63] || (|pte[62:61]) || pte[7] || pte[6] || pte[4];
    if(pte[63]) pte_invalid|=level_q!=0 || pte[13:10]!=4'b1000;
    permission=1;
    case(access_q)
      0,3:permission=pte[3];
      1:permission=pte[1] || (mxr_q && pte[3]);
      default:permission=pte[2];
    endcase
    if(gstage_q || privilege_q==0) permission&=pte[4];
    else if(privilege_q==1 && pte[4]) permission&=access_q!=0 && sum_q;
    permission&=pte[6] && (access_q!=2 || pte[7]);
    case(level_q)
      2:superpage_aligned=pte[27:10]==0;
      1:superpage_aligned=pte[18:10]==0;
      default:superpage_aligned=1;
    endcase
    case(level_q)
      2:leaf_address={pte[53:28],address_q[29:0]};
      1:leaf_address={pte[53:19],address_q[20:0]};
      default:leaf_address={pte[53:10],address_q[11:0]};
    endcase
    if(pte[63]) leaf_address={pte[53:14],address_q[15:0]};
  end
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      state_q<=IDLE;address_q<=0;table_q<=0;result_q<=0;level_q<=0;access_q<=0;
      privilege_q<=0;pbmt_q<=0;leaf_level_q<=0;gstage_q<=0;sum_q<=0;mxr_q<=0;
      pbmt_enable_q<=0;fault_q<=0;access_fault_q<=0;napot_q<=0;
    end else case(state_q)
      IDLE:if(req_valid_i) begin
        address_q<=req_address_i;table_q<={req_root_ppn_i,12'b0};level_q<=2;
        access_q<=req_access_i;privilege_q<=req_privilege_i;gstage_q<=req_gstage_i;
        sum_q<=req_sum_i;mxr_q<=req_mxr_i;pbmt_enable_q<=req_pbmt_enable_i;
        fault_q<=0;access_fault_q<=0;pbmt_q<=0;napot_q<=0;leaf_level_q<=0;
        if(req_bare_i) begin
          result_q<=req_address_i[55:0];state_q<=RESPONSE;
          fault_q<=(req_address_i>>PADDR_WIDTH)!=0;
          access_fault_q<=(req_address_i>>PADDR_WIDTH)!=0;
        end else if((req_gstage_i && ((req_address_i>>41)!=0 || req_root_ppn_i[1:0]!=0)) ||
                    (!req_gstage_i && req_address_i[63:39]!={25{req_address_i[38]}})) begin
          result_q<=0;fault_q<=1;state_q<=RESPONSE;
        end else state_q<=REQUEST;
      end
      REQUEST:if(mem_valid_o && mem_ready_i) state_q<=WAIT_PTE;
      WAIT_PTE:if(mem_response_valid_i) begin
        if(mem_response_error_i) begin
          fault_q<=1;access_fault_q<=1;result_q<=0;state_q<=RESPONSE;
        end else if(pte_invalid || (leaf && (!permission || !superpage_aligned)) || (!leaf && level_q==0)) begin
          fault_q<=1;result_q<=0;state_q<=RESPONSE;
        end else if(leaf) begin
          result_q<=leaf_address;pbmt_q<=pte[62:61];napot_q<=pte[63];leaf_level_q<=level_q;
          state_q<=RESPONSE;
          if((leaf_address>>PADDR_WIDTH)!=0) begin fault_q<=1;access_fault_q<=1;end
        end else begin
          table_q<={pte[53:10],12'b0};level_q<=level_q-1'b1;state_q<=REQUEST;
        end
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
      $stable({rsp_address_o,rsp_pbmt_o,rsp_fault_o,rsp_access_fault_o,rsp_leaf_level_o,rsp_napot_o}));
`endif
  initial if(PADDR_WIDTH<32 || PADDR_WIDTH>56) $fatal(1,"Invalid PTW physical width");
endmodule

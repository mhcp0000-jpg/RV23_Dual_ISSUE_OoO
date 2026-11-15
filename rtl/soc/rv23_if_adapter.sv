// Native 128-bit fetch: fall-through issue/response to two 64-bit bank ports.
// Capture the pair even when both ports stall; accepted work always drains.
module rv23_if_adapter(
  input logic clk_i,rst_ni,halt_i,req_valid_i,
  output logic req_ready_o,
  input logic [31:0] req_addr_i,
  input logic [3:0] req_id_i,req_epoch_i,
  input logic req_device_i=0,
  output logic rsp_valid_o,
  input logic rsp_ready_i,
  output logic [3:0] rsp_id_o,rsp_epoch_o,
  output logic [127:0] rsp_data_o,
  output logic [1:0] rsp_resp_o,
  output logic quiescent_o,
  rv_local_mem_if.requester bus,bus_hi
);
  import rv_soc_pkg::*;
  logic active_q,error_q,device_q;
  logic [1:0] sent_q,done_q,accepted,response_valid,response_ready,issue_valid;
  logic [1:0][63:0] held_data_q,response_data,merged_data;
  logic [1:0][1:0] held_code_q,response_code,merged_code;
  logic [31:0] addr_q,issue_addr;
  logic [3:0] id_q,epoch_q,issue_id;
  logic issue_new,new_good;
  assign response_valid={bus_hi.rsp_valid,bus.rsp_valid};
  assign response_data={bus_hi.rsp_rdata,bus.rsp_rdata};
  assign response_code={bus_hi.rsp_resp,bus.rsp_resp};
  for(genvar p=0;p<2;p++) begin
    assign merged_data[p]=done_q[p] ? held_data_q[p]:response_data[p];
    assign merged_code[p]=done_q[p] ? held_code_q[p]:response_code[p];
  end
  assign rsp_valid_o=active_q && (error_q || (&(done_q|response_valid)));
  assign rsp_data_o=error_q ? '0:{merged_data[1],merged_data[0]};
  assign rsp_resp_o=error_q ? AXI_RESP_DECERR:(merged_code[0]!=AXI_RESP_OKAY ? merged_code[0]:merged_code[1]);
  assign rsp_id_o=id_q;assign rsp_epoch_o=epoch_q;
  assign req_ready_o=rst_ni && !halt_i && (!active_q || (rsp_valid_o && rsp_ready_i));
  assign quiescent_o=!active_q || rsp_valid_o;
  assign issue_new=req_valid_i && req_ready_o;
  assign new_good=req_addr_i[3:0]==0 &&
    (addr_in_region(req_addr_i,rv23_pkg::SRAM_BASE,size_kb_to_bytes(rv23_pkg::SRAM_KB)) ||
     addr_in_region(req_addr_i,BOOTROM_BASE_ADDR,size_kb_to_bytes(BOOTROM_SIZE_KB)));
  assign issue_addr=issue_new ? req_addr_i:addr_q;
  assign issue_id=issue_new ? req_id_i:id_q;
  assign issue_valid=issue_new ? {2{new_good}}:({2{active_q && !error_q}} & ~sent_q);
  assign bus.req_valid=issue_valid[0];assign bus_hi.req_valid=issue_valid[1];
  assign bus.req_addr=issue_addr;assign bus_hi.req_addr=issue_addr+8;
  assign bus.req_id={2'b0,issue_id};assign bus_hi.req_id={2'b0,issue_id};
  assign bus.req_write=0;assign bus_hi.req_write=0;
  assign bus.req_size=3;assign bus_hi.req_size=3;
  assign bus.req_wdata=0;assign bus_hi.req_wdata=0;
  assign bus.req_wstrb=0;assign bus_hi.req_wstrb=0;
  assign bus.req_priv=PRIV_M;assign bus_hi.req_priv=PRIV_M;
  assign bus.req_rob_seq=0;assign bus_hi.req_rob_seq=0;
  assign bus.req_committed=0;assign bus_hi.req_committed=0;
  assign bus.req_device=issue_new ? req_device_i:device_q;
  assign bus_hi.req_device=issue_new ? req_device_i:device_q;
  assign accepted=issue_valid & {bus_hi.req_ready,bus.req_ready};
  assign response_ready={2{active_q && !error_q}} & ~done_q;
  assign bus.rsp_ready=response_ready[0];assign bus_hi.rsp_ready=response_ready[1];
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      active_q<=0;error_q<=0;sent_q<=0;done_q<=0;addr_q<=0;id_q<=0;epoch_q<=0;
      held_data_q<=0;held_code_q<=0;device_q<=0;
    end else begin
      sent_q<=sent_q|accepted;
      for(int p=0;p<2;p++) if(response_valid[p] && response_ready[p]) begin
        held_data_q[p]<=response_data[p];held_code_q[p]<=response_code[p];done_q[p]<=1;
      end
      if(rsp_valid_o && rsp_ready_i) begin active_q<=0;sent_q<=0;done_q<=0;end
      if(issue_new) begin
        active_q<=1;error_q<=!new_good;addr_q<=req_addr_i;id_q<=req_id_i;epoch_q<=req_epoch_i;
        device_q<=req_device_i;
        sent_q<=accepted;done_q<=0;held_data_q<=0;held_code_q<=0;
      end
    end
  end
endmodule

// One ordered physical PTE-read transport shared by IF and both LSU walkers.
// PMP and physical bounds are checked before a read can reach the cache/bus.
module rv23_ptw_arbiter #(
  parameter int unsigned ADDRESS_WIDTH=64,
  parameter int unsigned PADDR_WIDTH=32,
  parameter int unsigned PORTS=3,
  localparam int OWNER_W=$clog2(PORTS)
)(
  input logic clk_i,rst_ni,
  input logic [PORTS-1:0] req_valid_i,req_device_i,
  output logic [PORTS-1:0] req_ready_o,
  input logic [PORTS-1:0][55:0] req_address_i,
  output logic [PORTS-1:0] rsp_valid_o,
  input logic [PORTS-1:0] rsp_ready_i,
  output logic [PORTS-1:0][63:0] rsp_data_o,
  output logic [PORTS-1:0] rsp_error_o,
  input logic [7:0][7:0] pmpcfg_i,
  input logic [7:0][ADDRESS_WIDTH-3:0] pmpaddr_i,
  output logic bus_valid_o,
  input logic bus_ready_i,
  output logic [PADDR_WIDTH-1:0] bus_address_o,
  output logic bus_device_o,
  input logic bus_rsp_valid_i,
  output logic bus_rsp_ready_o,
  input logic [63:0] bus_rsp_data_i,
  input logic bus_rsp_error_i,
  output logic idle_o
);
  import rv_ooo_pkg::*;
  typedef enum logic [1:0] {IDLE,SEND,WAIT_DATA,ERROR} state_e;
  state_e state_q;
  logic [OWNER_W-1:0] owner_q,turn_q,grant;
  logic grant_valid,device_q;
  logic [PADDR_WIDTH-1:0] address_q;
  logic [PORTS-1:0][ADDRESS_WIDTH-1:0] physical;
  logic [PORTS-1:0][2:0] sizes,accesses;
  privilege_e [PORTS-1:0] privileges;
  logic [PORTS-1:0] allow_access;
  for(genvar p=0;p<PORTS;p++) begin
    assign physical[p]=ADDRESS_WIDTH'(req_address_i[p]);
    assign sizes[p]=3;assign accesses[p]=3'b001;assign privileges[p]=PRIV_S;
  end
  rv_pmp #(.PADDR_WIDTH(ADDRESS_WIDTH),.PMP_ENTRIES(8),.CHECK_PORTS(PORTS)) u_pmp (
    .pmpcfg_i,.pmpaddr_i,.check_valid_i(req_valid_i),.check_address_i(physical),
    .check_size_i(sizes),.check_access_i(accesses),.check_privilege_i(privileges),
    .allow_o(allow_access),.matched_o(),.fault_address_o());
  always_comb begin
    grant_valid=0;grant=0;
    for(int n=PORTS-1;n>=0;n--) begin
      if(req_valid_i[(int'(turn_q)+n)%PORTS]) begin
        grant_valid=1;grant=OWNER_W'((int'(turn_q)+n)%PORTS);
      end
    end
    req_ready_o=0;
    if(rst_ni && state_q==IDLE && grant_valid) req_ready_o[grant]=1;
    rsp_valid_o=0;rsp_data_o=0;rsp_error_o=0;
    if(state_q==ERROR) begin rsp_valid_o[owner_q]=1;rsp_error_o[owner_q]=1;end
    if(state_q==WAIT_DATA) begin
      rsp_valid_o[owner_q]=bus_rsp_valid_i;rsp_data_o[owner_q]=bus_rsp_data_i;
      rsp_error_o[owner_q]=bus_rsp_error_i;
    end
  end
  assign idle_o=state_q==IDLE;
  assign bus_valid_o=rst_ni && state_q==SEND;
  assign bus_address_o=address_q;assign bus_device_o=device_q;
  assign bus_rsp_ready_o=state_q==WAIT_DATA && rsp_ready_i[owner_q];
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin state_q<=IDLE;owner_q<=0;turn_q<=0;address_q<=0;device_q<=0;end
    else case(state_q)
      IDLE:if(grant_valid) begin
        owner_q<=grant;address_q<=PADDR_WIDTH'(req_address_i[grant]);device_q<=req_device_i[grant];
        turn_q<=int'(grant)==PORTS-1 ? '0:grant+1'b1;
        // Main SRAM is the implemented cacheable page-table PMA. Do not
        // truncate a wider physical address or issue PTE reads to MMIO.
        if((req_address_i[grant]>>PADDR_WIDTH)!=0 ||
           req_address_i[grant]<56'h80000000 || req_address_i[grant]>=56'h80100000 ||
           !allow_access[grant] || req_address_i[grant][2:0]!=0) state_q<=ERROR;
        else state_q<=SEND;
      end
      SEND:if(bus_ready_i) state_q<=WAIT_DATA;
      WAIT_DATA:if(bus_rsp_valid_i && rsp_ready_i[owner_q]) state_q<=IDLE;
      ERROR:if(rsp_ready_i[owner_q]) state_q<=IDLE;
      default:state_q<=IDLE;
    endcase
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    bus_valid_o && !bus_ready_i |=> bus_valid_o && $stable({bus_address_o,bus_device_o}));
`endif
endmodule

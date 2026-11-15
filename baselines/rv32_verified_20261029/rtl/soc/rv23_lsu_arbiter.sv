// One captured request at a time. Capturing the complete payload before
// asserting downstream valid prevents selection changes under backpressure.
module rv23_lsu_arbiter (
  input logic clk_i, rst_ni,
  output logic idle_o,
  rv_local_mem_if.target a, b,
  rv_local_mem_if.requester out_bus
);
  typedef enum logic [1:0] {IDLE, SEND, WAIT_RSP} state_t;
  state_t state_q;
  logic owner_q, turn_q, choose;
  logic [5:0] id_q;
  logic [31:0] addr_q;
  logic  write_q;
  logic [2:0] size_q;
  logic [63:0] wdata_q;
  logic [7:0] wstrb_q;
  rv_soc_pkg::privilege_e priv_q;
  logic [rv_ooo_pkg::ROB_SEQ_WIDTH-1:0] rob_seq_q;
  logic  committed_q;
  logic  device_q;
  assign choose = b.req_valid && (!a.req_valid || turn_q);
  assign idle_o = state_q == IDLE;
  assign a.req_ready = rst_ni && state_q == IDLE && !choose;
  assign b.req_ready = rst_ni && state_q == IDLE && choose;
  assign out_bus.req_valid = rst_ni && state_q == SEND;
  assign out_bus.req_id = id_q;
  assign out_bus.req_addr = addr_q;
  assign out_bus.req_write = write_q;
  assign out_bus.req_size = size_q;
  assign out_bus.req_wdata = wdata_q;
  assign out_bus.req_wstrb = wstrb_q;
  assign out_bus.req_priv = priv_q;
  assign out_bus.req_rob_seq = rob_seq_q;
  assign out_bus.req_committed = committed_q;
  assign out_bus.req_device = device_q;
  assign out_bus.rsp_ready = state_q == WAIT_RSP &&
    (owner_q ? b.rsp_ready : a.rsp_ready);
  assign a.rsp_valid = state_q == WAIT_RSP && !owner_q && out_bus.rsp_valid;
  assign b.rsp_valid = state_q == WAIT_RSP && owner_q && out_bus.rsp_valid;
  assign a.rsp_id = out_bus.rsp_id;
  assign a.rsp_rdata = out_bus.rsp_rdata;
  assign a.rsp_resp = out_bus.rsp_resp;
  assign a.rsp_replay = out_bus.rsp_replay;
  assign b.rsp_id = out_bus.rsp_id;
  assign b.rsp_rdata = out_bus.rsp_rdata;
  assign b.rsp_resp = out_bus.rsp_resp;
  assign b.rsp_replay = out_bus.rsp_replay;
  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      state_q <= IDLE; owner_q <= 0; turn_q <= 0;
      id_q <= '0;
      addr_q <= '0;
      write_q <= '0;
      size_q <= '0;
      wdata_q <= '0;
      wstrb_q <= '0;
      priv_q <= rv_soc_pkg::PRIV_M;
      rob_seq_q <= '0;
      committed_q <= '0;
      device_q <= '0;
    end else case (state_q)
      IDLE: if ((a.req_valid && a.req_ready) || (b.req_valid && b.req_ready)) begin
          owner_q <= choose; turn_q <= !choose;
          id_q <= choose ? b.req_id : a.req_id;
          addr_q <= choose ? b.req_addr : a.req_addr;
          write_q <= choose ? b.req_write : a.req_write;
          size_q <= choose ? b.req_size : a.req_size;
          wdata_q <= choose ? b.req_wdata : a.req_wdata;
          wstrb_q <= choose ? b.req_wstrb : a.req_wstrb;
          priv_q <= choose ? b.req_priv : a.req_priv;
          rob_seq_q <= choose ? b.req_rob_seq : a.req_rob_seq;
          committed_q <= choose ? b.req_committed : a.req_committed;
          device_q <= choose ? b.req_device : a.req_device;
          state_q <= SEND;
      end
      SEND: if (out_bus.req_valid && out_bus.req_ready) state_q <= WAIT_RSP;
      WAIT_RSP: if (out_bus.rsp_valid && out_bus.rsp_ready) state_q <= IDLE;
      default: state_q <= IDLE;
    endcase
  end
endmodule

// Shared SRAM behind the main AXI bus, never an ITIM/DTIM side path.
module rv23_sram #(
  parameter logic [31:0] BASE_ADDR = rv23_pkg::SRAM_BASE,
  parameter int unsigned SIZE_KB = rv23_pkg::SRAM_KB,
  parameter string INIT_FILE = "",
  localparam int unsigned DEPTH = SIZE_KB * 1024 / 8,
  localparam int unsigned ROW_W = $clog2(DEPTH)
) (
  input logic clk_i, rst_ni,
  output logic write_snoop_o,
  output logic [31:0] write_snoop_addr_o,
  output logic [63:0] write_snoop_data_o,
  output logic [7:0] write_snoop_strb_o,
  rv_local_mem_if.target bus
);
  import rv_soc_pkg::*;
  typedef enum logic [1:0] {IDLE, READ_WAIT, RESP} state_t;
  state_t state_q;
  logic [5:0] id_q;
  logic [63:0] data_q, mem_data;
  axi_resp_e code_q;
  logic mem_valid;
  wire [31:0] offset = bus.req_addr - BASE_ADDR;
  wire good = addr_in_region(bus.req_addr,BASE_ADDR,size_kb_to_bytes(SIZE_KB)) &&
    bus.req_size <= 3 && ((bus.req_addr & ((32'd1 << bus.req_size)-1)) == 0) &&
    (!bus.req_write || bus.req_committed);
  wire accept = bus.req_valid && bus.req_ready;
  assign bus.req_ready = rst_ni && state_q == IDLE;
  assign bus.rsp_valid = state_q == RESP;
  assign bus.rsp_id = id_q; assign bus.rsp_rdata = data_q;
  assign bus.rsp_resp = code_q; assign bus.rsp_replay = MEM_REPLAY_NONE;
  assign write_snoop_o = accept && good && bus.req_write && (|bus.req_wstrb);
  assign write_snoop_addr_o = bus.req_addr;
  assign write_snoop_data_o = bus.req_wdata;
  assign write_snoop_strb_o = bus.req_wstrb;
  rv_sram_1r1w #(.DEPTH(DEPTH),.INIT_FILE(INIT_FILE)) u_mem (
    .clk_i,.rst_ni,
    .read_en_i(accept && good && !bus.req_write),
    .read_addr_i(offset[3 +: ROW_W]),
    .read_valid_o(mem_valid),.read_data_o(mem_data),
    .write_en_i(write_snoop_o),.write_addr_i(offset[3 +: ROW_W]),
    .write_data_i(bus.req_wdata),.write_strb_i(bus.req_wstrb)
  );
  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      state_q <= IDLE; id_q <= 0; data_q <= 0; code_q <= AXI_RESP_OKAY;
    end else case (state_q)
      IDLE: if (accept) begin
        id_q <= bus.req_id; data_q <= 0;
        code_q <= good ? AXI_RESP_OKAY : AXI_RESP_SLVERR;
        state_q <= !good || bus.req_write ? RESP : READ_WAIT;
      end
      READ_WAIT: if (mem_valid) begin data_q <= mem_data; state_q <= RESP; end
      RESP: if (bus.rsp_ready) state_q <= IDLE;
      default: state_q <= IDLE;
    endcase
  end
  initial begin
    if (DEPTH < 2 || (DEPTH & (DEPTH-1)) != 0 || BASE_ADDR[2:0] != 0)
      $fatal(1,"Invalid shared SRAM geometry");
  end
endmodule

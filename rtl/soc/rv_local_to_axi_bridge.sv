module rv_local_to_axi_bridge #(
  parameter int unsigned ADDR_WIDTH       = 32,
  parameter int unsigned DATA_WIDTH       = 64,
  parameter int unsigned LOCAL_ID_WIDTH   = 6,
  parameter int unsigned AXI_ID_WIDTH     = 4,
  parameter int unsigned ROB_SEQ_WIDTH    = rv_ooo_pkg::ROB_SEQ_WIDTH,
  parameter int unsigned AXI_PROGRESS_TIMEOUT_CYCLES =
    rv_soc_pkg::AXI_PROGRESS_TIMEOUT_CYCLES,
  parameter bit          IS_INSTRUCTION   = 1'b0,
  parameter bit          CACHE_BURST      = 1'b0,
  parameter logic [31:0] CACHE_BASE_ADDR   = 32'h80000000,
  parameter int unsigned CACHE_MEMORY_KB  = 1024
) (
  input  logic                   clk_i,
  input  logic                   rst_ni,
  input  logic                   refill_i,
  output logic                   idle_o,
  rv_local_mem_if.target         local_bus,
  rv_axi4_if.master              axi_m
);

  import rv_soc_pkg::*;

  typedef enum logic [3:0] {
    BR_IDLE,
    BR_WRITE_SEND,
    BR_WRITE_RESP,
    BR_READ_ADDR,
    BR_READ_DATA,
    BR_DRAIN_WRITE_SEND,
    BR_DRAIN_WRITE_RESP,
    BR_DRAIN_READ_DATA,
    BR_FILL_ADDR,
    BR_FILL_DATA,
    BR_FILL_REPLAY,
    BR_FILL_DRAIN
  } bridge_state_e;

  localparam int unsigned TIMEOUT_COUNTER_WIDTH =
    (AXI_PROGRESS_TIMEOUT_CYCLES <= 1) ? 1 :
    $clog2(AXI_PROGRESS_TIMEOUT_CYCLES + 1);
  localparam int unsigned TIMEOUT_LIMIT =
    (AXI_PROGRESS_TIMEOUT_CYCLES == 0) ? 0 :
    AXI_PROGRESS_TIMEOUT_CYCLES - 1;

  bridge_state_e state_q;
  logic [LOCAL_ID_WIDTH-1:0] local_id_q;
  logic [ADDR_WIDTH-1:0] address_q;
  logic [2:0] size_q;
  logic [DATA_WIDTH-1:0] write_data_q;
  logic [DATA_WIDTH/8-1:0] write_strb_q;
  privilege_e privilege_q;
  logic device_q;
  logic committed_q;
  logic aw_sent_q;
  logic w_sent_q;
  logic aw_fire;
  logic w_fire;
  logic [AXI_ID_WIDTH-1:0] axi_id_q;
  logic [DATA_WIDTH-1:0] response_data_q;
  axi_resp_e response_code_q;
  logic local_response_valid_q;
  logic [TIMEOUT_COUNTER_WIDTH-1:0] timeout_count_q;
  logic timeout_expired;
  logic aw_complete;
  logic w_complete;
  // A transient refill transport buffer, never a separately addressable cache.
  // Payload is not reset. The cache still owns tags, invalidation and banking.
  logic [63:0] fill_data_q [0:7];
  logic [7:0] fill_valid_q;
  logic [3:0] fill_received_q, fill_next_q;
  logic fill_pending_q, fill_done_q, fill_error_q;
  wire fill_active = state_q inside {BR_FILL_ADDR, BR_FILL_DATA,
                                    BR_FILL_REPLAY, BR_FILL_DRAIN};
  wire fill_request_match = !local_bus.req_write && !local_bus.req_device &&
    local_bus.req_size == 3 && local_bus.req_addr ==
      address_q + (32'(fill_next_q) << 3) &&
    local_bus.req_priv == privilege_q &&
    AXI_ID_WIDTH'(local_bus.req_id) == axi_id_q;
  wire fill_eligible = CACHE_BURST && refill_i &&
    !local_bus.req_write && !local_bus.req_device && local_bus.req_size == 3 &&
    local_bus.req_addr[5:0] == 0 &&
    addr_in_region(local_bus.req_addr, CACHE_BASE_ADDR,
                   size_kb_to_bytes(CACHE_MEMORY_KB));

  function automatic logic request_is_aligned(
    input logic [ADDR_WIDTH-1:0] request_address,
    input logic [2:0] request_size
  );
    logic [ADDR_WIDTH-1:0] byte_mask;
    if (request_size > 3)
      return 1'b0;
    byte_mask = ({{(ADDR_WIDTH-1){1'b0}}, 1'b1} << request_size) - 1;
    return (request_address & byte_mask) == 0;
  endfunction

  assign idle_o = (state_q == BR_IDLE) && !local_response_valid_q;
  assign local_bus.req_ready  = !local_response_valid_q &&
    ((state_q == BR_IDLE) ||
     (fill_active && !fill_pending_q && !fill_done_q &&
      (fill_error_q || !fill_request_match ||
       (fill_next_q < 8 && fill_valid_q[fill_next_q[2:0]]))));
  assign local_bus.rsp_valid  = local_response_valid_q;
  assign local_bus.rsp_id     = local_id_q;
  assign local_bus.rsp_rdata  = response_data_q;
  assign local_bus.rsp_resp   = response_code_q;
  assign local_bus.rsp_replay = MEM_REPLAY_NONE;

  assign aw_fire = axi_m.aw_valid && axi_m.aw_ready;
  assign w_fire  = axi_m.w_valid && axi_m.w_ready;
  assign aw_complete = aw_sent_q || aw_fire;
  assign w_complete  = w_sent_q || w_fire;
  assign timeout_expired = (AXI_PROGRESS_TIMEOUT_CYCLES != 0) &&
    (timeout_count_q >= TIMEOUT_COUNTER_WIDTH'(TIMEOUT_LIMIT));

  always_comb begin
    axi_m.aw_id    = axi_id_q;
    axi_m.aw_addr  = address_q;
    axi_m.aw_len   = 8'd0;
    axi_m.aw_size  = size_q;
    axi_m.aw_burst = 2'b01;
    axi_m.aw_lock = 1'b0;
    axi_m.aw_prot  = {IS_INSTRUCTION, 1'b0,
                      (privilege_q != PRIV_U)};
    axi_m.aw_cache = device_q ? 4'b0000 : 4'b0011;
    axi_m.aw_qos   = '0;
    axi_m.aw_valid = ((state_q == BR_WRITE_SEND) ||
                      (state_q == BR_DRAIN_WRITE_SEND)) && !aw_sent_q;

    axi_m.w_data   = write_data_q;
    axi_m.w_strb   = write_strb_q;
    axi_m.w_last   = 1'b1;
    axi_m.w_valid  = ((state_q == BR_WRITE_SEND) ||
                      (state_q == BR_DRAIN_WRITE_SEND)) && !w_sent_q;
    axi_m.b_ready  = (state_q == BR_WRITE_RESP) ||
                     (state_q == BR_DRAIN_WRITE_RESP);

    axi_m.ar_id    = axi_id_q;
    axi_m.ar_addr  = address_q;
    axi_m.ar_len   = fill_active ? 8'd7 : 8'd0;
    axi_m.ar_size  = size_q;
    axi_m.ar_burst = 2'b01;
    axi_m.ar_lock = 1'b0;
    axi_m.ar_prot  = {IS_INSTRUCTION, 1'b0,
                      (privilege_q != PRIV_U)};
    axi_m.ar_cache = device_q ? 4'b0000 : 4'b0011;
    axi_m.ar_qos   = '0;
    axi_m.ar_valid = (state_q == BR_READ_ADDR) || (state_q == BR_FILL_ADDR);
    axi_m.r_ready  = (state_q == BR_READ_DATA) ||
                     (state_q == BR_DRAIN_READ_DATA) ||
                     (state_q == BR_FILL_DATA) || (state_q == BR_FILL_DRAIN);
  end

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      state_q         <= BR_IDLE;
      local_id_q      <= '0;
      address_q       <= '0;
      size_q          <= '0;
      write_data_q    <= '0;
      write_strb_q    <= '0;
      privilege_q     <= PRIV_M;
      device_q        <= 1'b0;
      committed_q     <= 1'b0;
      aw_sent_q       <= 1'b0;
      w_sent_q        <= 1'b0;
      axi_id_q        <= '0;
      response_data_q <= '0;
      response_code_q <= AXI_RESP_OKAY;
      local_response_valid_q <= 1'b0;
      timeout_count_q <= '0;
      fill_valid_q <= '0;
      fill_received_q <= '0;
      fill_next_q <= '0;
      fill_pending_q <= 1'b0;
      fill_done_q <= 1'b0;
      fill_error_q <= 1'b0;
    end else begin
      if (local_response_valid_q && local_bus.rsp_ready)
        local_response_valid_q <= 1'b0;

      if (fill_active) begin
        if (local_bus.req_valid && local_bus.req_ready) begin
          local_id_q <= local_bus.req_id;
          fill_pending_q <= 1'b1;
          if (!fill_request_match) fill_error_q <= 1'b1;
        end
        // Register each local response so downstream stalls cannot change it.
        if (fill_pending_q && !local_response_valid_q &&
            (fill_error_q || fill_valid_q[fill_next_q[2:0]])) begin
          response_data_q <= fill_error_q ? '0 : fill_data_q[fill_next_q[2:0]];
          response_code_q <= fill_error_q ? AXI_RESP_SLVERR : AXI_RESP_OKAY;
          local_response_valid_q <= 1'b1;
          fill_pending_q <= 1'b0;
          fill_next_q <= fill_next_q + 1'b1;
          if (fill_error_q || fill_next_q == 7) fill_done_q <= 1'b1;
        end
      end

      case (state_q)
        BR_IDLE: begin
          timeout_count_q <= '0;
          if (local_bus.req_valid && local_bus.req_ready) begin
            local_id_q   <= local_bus.req_id;
            address_q    <= local_bus.req_addr;
            size_q       <= local_bus.req_size;
            write_data_q <= local_bus.req_wdata;
            write_strb_q <= local_bus.req_wstrb;
            privilege_q  <= local_bus.req_priv;
            device_q     <= local_bus.req_device;
            committed_q  <= local_bus.req_committed;
            axi_id_q     <= AXI_ID_WIDTH'(local_bus.req_id);
            aw_sent_q    <= 1'b0;
            w_sent_q     <= 1'b0;
            if (!request_is_aligned(local_bus.req_addr,
                                    local_bus.req_size)) begin
              response_data_q <= '0;
              response_code_q <= AXI_RESP_SLVERR;
              local_response_valid_q <= 1'b1;
              state_q         <= BR_IDLE;
            end else if (local_bus.req_write) begin
              state_q <= BR_WRITE_SEND;
            end else if (fill_eligible) begin
              state_q <= BR_FILL_ADDR;
              fill_valid_q <= '0;
              fill_received_q <= '0;
              fill_next_q <= '0;
              fill_pending_q <= 1'b1;
              fill_done_q <= 1'b0;
              fill_error_q <= 1'b0;
            end else begin
              state_q <= BR_READ_ADDR;
            end
          end
        end

        BR_WRITE_SEND: begin
          if (aw_fire)
            aw_sent_q <= 1'b1;
          if (w_fire)
            w_sent_q <= 1'b1;
          if (aw_complete && w_complete) begin
            state_q <= BR_WRITE_RESP;
            timeout_count_q <= '0;
          end else if (timeout_expired) begin
            response_data_q <= '0;
            response_code_q <= AXI_RESP_SLVERR;
            local_response_valid_q <= 1'b1;
            timeout_count_q <= '0;
            // Neither channel handshook, so cancellation is still AXI-safe.
            // If one channel was accepted, finish and drain the orphaned
            // transaction without associating its late response with a new ID.
            state_q <= (aw_complete || w_complete) ?
                       BR_DRAIN_WRITE_SEND : BR_IDLE;
          end else if (aw_fire || w_fire) begin
            timeout_count_q <= '0;
          end else begin
            timeout_count_q <= timeout_count_q + 1'b1;
          end
        end

        BR_WRITE_RESP: begin
          if (axi_m.b_valid && axi_m.b_ready) begin
            response_data_q <= '0;
            response_code_q <= (axi_m.b_id == axi_id_q) ?
                               axi_resp_e'(axi_m.b_resp) : AXI_RESP_SLVERR;
            local_response_valid_q <= 1'b1;
            state_q <= BR_IDLE;
            timeout_count_q <= '0;
          end else if (timeout_expired) begin
            response_data_q <= '0;
            response_code_q <= AXI_RESP_SLVERR;
            local_response_valid_q <= 1'b1;
            state_q <= BR_DRAIN_WRITE_RESP;
            timeout_count_q <= '0;
          end else begin
            timeout_count_q <= timeout_count_q + 1'b1;
          end
        end

        BR_READ_ADDR: begin
          if (axi_m.ar_valid && axi_m.ar_ready) begin
            state_q <= BR_READ_DATA;
            timeout_count_q <= '0;
          end else if (timeout_expired) begin
            // AR was never accepted, so the request can be cancelled locally.
            response_data_q <= '0;
            response_code_q <= AXI_RESP_SLVERR;
            local_response_valid_q <= 1'b1;
            state_q <= BR_IDLE;
            timeout_count_q <= '0;
          end else begin
            timeout_count_q <= timeout_count_q + 1'b1;
          end
        end

        BR_READ_DATA: begin
          if (axi_m.r_valid && axi_m.r_ready) begin
            response_data_q <= axi_m.r_data;
            if ((axi_m.r_id != axi_id_q) || !axi_m.r_last)
              response_code_q <= AXI_RESP_SLVERR;
            else
              response_code_q <= axi_resp_e'(axi_m.r_resp);
            local_response_valid_q <= 1'b1;
            state_q <= BR_IDLE;
            timeout_count_q <= '0;
          end else if (timeout_expired) begin
            response_data_q <= '0;
            response_code_q <= AXI_RESP_SLVERR;
            local_response_valid_q <= 1'b1;
            state_q <= BR_DRAIN_READ_DATA;
            timeout_count_q <= '0;
          end else begin
            timeout_count_q <= timeout_count_q + 1'b1;
          end
        end

        BR_DRAIN_WRITE_SEND: begin
          if (aw_fire)
            aw_sent_q <= 1'b1;
          if (w_fire)
            w_sent_q <= 1'b1;
          if (aw_complete && w_complete)
            state_q <= BR_DRAIN_WRITE_RESP;
        end

        BR_DRAIN_WRITE_RESP: begin
          if (axi_m.b_valid && axi_m.b_ready)
            state_q <= BR_IDLE;
        end

        BR_DRAIN_READ_DATA: begin
          if (axi_m.r_valid && axi_m.r_ready)
            state_q <= BR_IDLE;
        end

        BR_FILL_ADDR: begin
          if (axi_m.ar_ready) begin
            state_q <= fill_error_q ? BR_FILL_DRAIN : BR_FILL_DATA;
            timeout_count_q <= '0;
          end else if (!fill_error_q) begin
            if (timeout_expired) begin
              // Keep AR stable until accepted, even after the local timeout.
              fill_error_q <= 1'b1;
              timeout_count_q <= '0;
            end else timeout_count_q <= timeout_count_q + 1'b1;
          end
        end

        BR_FILL_DATA: begin
          if (axi_m.r_valid) begin
            timeout_count_q <= '0;
            if (axi_m.r_id != axi_id_q || axi_m.r_resp != AXI_RESP_OKAY ||
                axi_m.r_last != (fill_received_q == 7)) begin
              fill_error_q <= 1'b1;
              state_q <= axi_m.r_last ? BR_FILL_REPLAY : BR_FILL_DRAIN;
            end else begin
              fill_data_q[fill_received_q[2:0]] <= axi_m.r_data;
              fill_valid_q[fill_received_q[2:0]] <= 1'b1;
              fill_received_q <= fill_received_q + 1'b1;
              if (axi_m.r_last) state_q <= BR_FILL_REPLAY;
            end
          end else if (timeout_expired) begin
            fill_error_q <= 1'b1;
            state_q <= BR_FILL_DRAIN;
            timeout_count_q <= '0;
          end else timeout_count_q <= timeout_count_q + 1'b1;
        end

        BR_FILL_DRAIN: begin
          if (axi_m.r_valid && axi_m.r_last) state_q <= BR_FILL_REPLAY;
        end

        BR_FILL_REPLAY: begin
          if (fill_done_q && !local_response_valid_q) state_q <= BR_IDLE;
        end

        default: state_q <= BR_IDLE;
      endcase
    end
  end

`ifndef SYNTHESIS
  property p_single_beat_write;
    @(posedge clk_i) disable iff (!rst_ni)
      axi_m.w_valid |-> axi_m.w_last;
  endproperty
  assert property (p_single_beat_write);

  property p_no_axi_write_for_uncommitted_store;
    @(posedge clk_i) disable iff (!rst_ni)
      (axi_m.aw_valid || axi_m.w_valid) |-> committed_q;
  endproperty
  assert property (p_no_axi_write_for_uncommitted_store);
`endif

  initial begin : p_parameter_checks
    if ((DATA_WIDTH != 64) || (ADDR_WIDTH != 32))
      $fatal(1, "M1 bridge baseline requires AXI32/64");
    if ((AXI_ID_WIDTH == 0) || (LOCAL_ID_WIDTH == 0))
      $fatal(1, "Bridge ID widths must be nonzero");
  end

endmodule

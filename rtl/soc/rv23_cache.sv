// Two 64-bit 1R1W banks (address[3]), 32 KiB total. One-cycle resident reads.
// Two independent CPU ports; one shared miss/write-through AXI64 engine.
module rv23_cache #(
  parameter int unsigned SIZE_KB=32,
  parameter logic [31:0] BASE_ADDR=rv23_pkg::SRAM_BASE,
  parameter int unsigned MEMORY_KB=rv23_pkg::SRAM_KB,
  parameter bit READ_ONLY=0,
  parameter bit QUEUE_WRITES=0,
  localparam int unsigned LINES=SIZE_KB*1024/64,
  localparam int unsigned INDEX_W=$clog2(LINES),
  localparam int unsigned TAG_W=32-INDEX_W-6,
  localparam int unsigned ROW_W=INDEX_W+2
)(
  input logic clk_i,rst_ni,invalidate_i,snoop_valid_i,
  input logic [31:0] snoop_addr_i,
  input logic [63:0] snoop_wdata_i,
  input logic [7:0] snoop_wstrb_i,
  output logic idle_o,
  output logic refill_o,
  rv_local_mem_if.target cpu,cpu_b,
  rv_local_mem_if.requester mem
);
  import rv_soc_pkg::*;
  typedef enum logic [1:0] {IDLE,SEND,WAIT_MEM} state_t;
  state_t state_q;
  logic [LINES-1:0] valid_q;
  logic [TAG_W-1:0] tags[0:LINES-1];
  logic [63:0] data_bank0[0:LINES*4-1],data_bank1[0:LINES*4-1];
  logic [1:0] busy_q,response_valid_q;
  logic [1:0][5:0] response_id_q;
  logic [1:0][63:0] response_data_q;
  logic [1:0][1:0] response_code_q;
  logic turn_q,owner_q;
  logic [31:0] addr_q;
  logic [5:0] id_q;
  logic write_q,device_q,committed_q,cached_q,filling_q,killed_q;
  logic [2:0] size_q,beat_q;
  logic [63:0] wdata_q,selected_data_q;
  logic [7:0] wstrb_q;
  privilege_e priv_q;
  logic [rv_ooo_pkg::ROB_SEQ_WIDTH-1:0] seq_q;
  wire [INDEX_W-1:0] index=addr_q[6+:INDEX_W];
  wire [TAG_W-1:0] tag_value=addr_q[31-:TAG_W];
  wire [INDEX_W-1:0] snoop_index=snoop_addr_i[6+:INDEX_W];
  wire snoop_resident=snoop_valid_i && valid_q[snoop_index] && tags[snoop_index]==snoop_addr_i[31-:TAG_W];
  wire snoop_update=!READ_ONLY && snoop_resident && (|snoop_wstrb_i);
  wire invalidate_request=invalidate_i || (snoop_valid_i && snoop_addr_i[31:6]==addr_q[31:6]);
  logic [1:0] req_valid,req_write,req_committed,req_device,rsp_ready;
  logic [1:0][31:0] req_addr;
  logic [1:0][5:0] req_id;
  logic [1:0][2:0] req_size;
  logic [1:0][63:0] req_wdata;
  logic [1:0][7:0] req_wstrb;
  logic [1:0][1:0] req_priv;
  logic [1:0][rv_ooo_pkg::ROB_SEQ_WIDTH-1:0] req_seq;
  logic [1:0][INDEX_W-1:0] req_index;
  logic [1:0][ROW_W-1:0] req_row;
  logic [1:0] available,bad,cacheable,hit,eligible,engine_candidate;
  logic [1:0] accept,hit_accept,miss_accept,write_accept,engine_grant,ready;
  logic [1:0] bank_read_en,bank_read_owner;
  logic [1:0][ROW_W-1:0] bank_read_row;
  logic engine_accept,engine_port;
  logic [1:0] forward_response;
  typedef struct packed {
    logic [31:0] address;
    logic [63:0] data;
    logic [7:0] strobe;
    logic [5:0] id;
    logic [2:0] size;
    privilege_e privilege;
    logic [rv_ooo_pkg::ROB_SEQ_WIDTH-1:0] seq;
  } queued_write_t;
  queued_write_t write_queue[4];
  logic [2:0] write_count_q;
  logic [1:0] write_head_q,write_tail_q;
  logic queued_owner_q,queued_response_q;
  axi_resp_e queued_code_q;
  logic [5:0] queued_id_q;
  logic [1:0] queued_word_conflict;
  wire queued_offer=QUEUE_WRITES && req_write[0] && cacheable[0] && !bad[0];
  wire enqueue_write=queued_offer && accept[0];
  wire finish_write=state_q==WAIT_MEM && queued_owner_q && mem.rsp_valid && mem.rsp_ready;
  wire return_queued_write=(queued_response_q || finish_write) && !busy_q[0];
  wire launch_queued_write=state_q==IDLE && !queued_response_q &&
    (write_count_q!=0 || enqueue_write);
  queued_write_t incoming_write,issued_write;
  assign incoming_write='{req_addr[0],req_wdata[0],req_wstrb[0],req_id[0],
    req_size[0],privilege_e'(req_priv[0]),req_seq[0]};
  assign issued_write=write_count_q==0 ? incoming_write:write_queue[write_head_q];
  wire [1:0] bus_response_code=mem.rsp_resp==AXI_RESP_OKAY && mem.rsp_replay!=MEM_REPLAY_NONE ?
    AXI_RESP_SLVERR:mem.rsp_resp;
  wire [63:0] bus_response_data=bus_response_code==AXI_RESP_OKAY ? mem.rsp_rdata:64'b0;
  wire launch=state_q==IDLE && engine_accept;
  wire launch_fill=cacheable[engine_port] && !req_write[engine_port];
  wire fill_write=state_q==WAIT_MEM && mem.rsp_valid && mem.rsp_ready && filling_q &&
    mem.rsp_resp==AXI_RESP_OKAY && mem.rsp_replay==MEM_REPLAY_NONE;
  assign req_valid={cpu_b.req_valid,cpu.req_valid};
  assign req_addr={cpu_b.req_addr,cpu.req_addr};
  assign req_id={cpu_b.req_id,cpu.req_id};
  assign req_write={cpu_b.req_write,cpu.req_write};
  assign req_size={cpu_b.req_size,cpu.req_size};
  assign req_wdata={cpu_b.req_wdata,cpu.req_wdata};
  assign req_wstrb={cpu_b.req_wstrb,cpu.req_wstrb};
  assign req_priv={cpu_b.req_priv,cpu.req_priv};
  assign req_seq={cpu_b.req_rob_seq,cpu.req_rob_seq};
  assign req_committed={cpu_b.req_committed,cpu.req_committed};
  assign req_device={cpu_b.req_device,cpu.req_device};
  assign rsp_ready={cpu_b.rsp_ready,cpu.rsp_ready};
  assign cpu.req_ready=ready[0];assign cpu_b.req_ready=ready[1];
  assign cpu.rsp_valid=response_valid_q[0] || forward_response[0] || return_queued_write;
  assign cpu_b.rsp_valid=response_valid_q[1] || forward_response[1];
  assign cpu.rsp_id=return_queued_write ? (finish_write ? id_q:queued_id_q):response_id_q[0];
  assign cpu_b.rsp_id=response_id_q[1];
  assign cpu.rsp_rdata=return_queued_write ? 64'b0:
    (forward_response[0] ? bus_response_data:response_data_q[0]);
  assign cpu_b.rsp_rdata=forward_response[1] ? bus_response_data:response_data_q[1];
  assign cpu.rsp_resp=return_queued_write ? (finish_write ? axi_resp_e'(bus_response_code):queued_code_q) :
    axi_resp_e'(forward_response[0] ? bus_response_code:response_code_q[0]);
  assign cpu_b.rsp_resp=axi_resp_e'(forward_response[1] ? bus_response_code:response_code_q[1]);
  assign cpu.rsp_replay=MEM_REPLAY_NONE;assign cpu_b.rsp_replay=MEM_REPLAY_NONE;
  assign idle_o=state_q==IDLE && !(|busy_q) && write_count_q==0 && !queued_response_q;
  assign refill_o=launch ? launch_fill : filling_q;
  for(genvar p=0;p<2;p++) begin:g_request_attributes
    assign bad[p]=req_size[p]>3 || ((req_addr[p]&((32'd1<<req_size[p])-1))!=0) ||
      (req_write[p] && (!req_committed[p] || READ_ONLY));
    assign cacheable[p]=!req_device[p] &&
      addr_in_region(req_addr[p],BASE_ADDR,size_kb_to_bytes(MEMORY_KB));
  end
  always_comb begin
    for(int p=0;p<2;p++) begin
      req_index[p]=req_addr[p][6+:INDEX_W];req_row[p]={req_index[p],req_addr[p][5:4]};
      available[p]=!busy_q[p] || (response_valid_q[p] && rsp_ready[p]);
      hit[p]=!req_write[p] && cacheable[p] && valid_q[req_index[p]] && tags[req_index[p]]==req_addr[p][31-:TAG_W];
      queued_word_conflict[p]=0;
      for(int i=0;i<4;i++)
        if(i<int'(write_count_q) &&
           write_queue[2'(write_head_q+i)].address[31:3]==req_addr[p][31:3])
          queued_word_conflict[p]=1;
      eligible[p]=rst_ni && available[p] && !invalidate_i &&
        !(p==0 && return_queued_write) &&
        !(hit[p] && queued_word_conflict[p]) &&
        !(snoop_valid_i && snoop_addr_i[31:6]==req_addr[p][31:6]) &&
        // Only the word being written needs to await write-through completion.
        // Other resident words of the same line have independent SRAM rows.
        !(state_q!=IDLE && write_q && addr_q[31:3]==req_addr[p][31:3]);
      engine_candidate[p]=req_valid[p] && eligible[p] && !bad[p] && !hit[p] &&
        write_count_q==0 && !queued_response_q && !(p==0 && queued_offer);
    end
    if(req_valid[0] && queued_offer && eligible[0] && write_count_q<4)
      engine_candidate[1]=0;
    engine_grant=0;
    if(state_q==IDLE) begin
      if(engine_candidate[turn_q]) engine_grant[turn_q]=1;
      else if(engine_candidate[!turn_q]) engine_grant[!turn_q]=1;
    end
    for(int p=0;p<2;p++) ready[p]=eligible[p] && (bad[p] || hit[p] || engine_grant[p]);
    if(queued_offer) ready[0]=eligible[0] && write_count_q<4;
    if(req_valid[0] && queued_offer && ready[0] && hit[1] && req_addr[0][31:3]==req_addr[1][31:3])
      ready[1]=0;
    if(req_valid[0] && req_valid[1] && eligible[0] && eligible[1] && hit[0] && hit[1] &&
      !bad[0] && !bad[1] && req_addr[0][3]==req_addr[1][3]) ready[!turn_q]=0;
    accept=req_valid & ready;hit_accept=accept & hit & ~bad;
    miss_accept=accept & cacheable & ~req_write & ~hit & ~bad;
    write_accept=accept & req_write & ~bad;
    engine_accept=|(accept & engine_grant);engine_port=engine_grant[1];
    bank_read_en=0;bank_read_owner=0;bank_read_row=0;
    for(int p=0;p<2;p++) if(hit_accept[p]) begin
      bank_read_en[req_addr[p][3]]=1;bank_read_owner[req_addr[p][3]]=1'(p);
      bank_read_row[req_addr[p][3]]=req_row[p];
    end
  end
  // Fall through on the first engine request. A stalled offer is captured at
  // the CPU acceptance edge and SEND holds exactly that payload until ready.
  // No completion is bypassed: write-through still waits for the bus response.
  assign mem.req_valid=rst_ni && (state_q==SEND || launch || launch_queued_write);
  assign mem.req_id=launch_queued_write ? issued_write.id:(launch ? req_id[engine_port]:id_q);
  assign mem.req_addr=launch_queued_write ? issued_write.address:
    launch ? (launch_fill ? {req_addr[engine_port][31:6],6'b0}:req_addr[engine_port]):
    (filling_q ? {addr_q[31:6],beat_q,3'b0}:addr_q);
  assign mem.req_write=launch_queued_write || (launch ? req_write[engine_port]:write_q);
  assign mem.req_size=launch_queued_write ? issued_write.size:
    launch ? (launch_fill ? 3'd3:req_size[engine_port]):(filling_q ? 3'd3:size_q);
  assign mem.req_wdata=launch_queued_write ? issued_write.data:(launch ? req_wdata[engine_port]:wdata_q);
  assign mem.req_wstrb=launch_queued_write ? issued_write.strobe:(launch ? req_wstrb[engine_port]:wstrb_q);
  assign mem.req_priv=launch_queued_write ? issued_write.privilege:
    (launch ? privilege_e'(req_priv[engine_port]):priv_q);
  assign mem.req_rob_seq=launch_queued_write ? issued_write.seq:(launch ? req_seq[engine_port]:seq_q);
  assign mem.req_committed=launch_queued_write || (launch ? req_committed[engine_port]:committed_q);
  assign mem.req_device=!launch_queued_write && (launch ? req_device[engine_port]:device_q);
  // Stall a refill response if its bank write port is used by a snoop merge.
  assign mem.rsp_ready=state_q==WAIT_MEM && !(filling_q && snoop_update && snoop_addr_i[3]==beat_q[0]);
  // The bridge already registers its bus response. For writes and uncached
  // reads it can be delivered directly; a stalled CPU gets a holding copy.
  // Refills retain the registered completion so tag/data install precedes use.
  always_comb begin
    forward_response=0;
    if(rst_ni && state_q==WAIT_MEM && !filling_q && !queued_owner_q && mem.rsp_valid)
      forward_response[owner_q]=1;
  end
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      state_q<=IDLE;valid_q<=0;busy_q<=0;response_valid_q<=0;
      response_id_q<=0;response_data_q<=0;response_code_q<=0;
      turn_q<=0;owner_q<=0;addr_q<=0;id_q<=0;write_q<=0;device_q<=0;
      committed_q<=0;cached_q<=0;filling_q<=0;killed_q<=0;size_q<=0;beat_q<=0;
      wdata_q<=0;wstrb_q<=0;priv_q<=PRIV_M;seq_q<=0;selected_data_q<=0;
      write_count_q<=0;write_head_q<=0;write_tail_q<=0;
      queued_owner_q<=0;queued_response_q<=0;queued_id_q<=0;queued_code_q<=AXI_RESP_OKAY;
    end else begin
      case({enqueue_write,finish_write})
        2'b10: write_count_q<=write_count_q+1'b1;
        2'b01: write_count_q<=write_count_q-1'b1;
        default: begin end
      endcase
      if(enqueue_write) begin
        write_queue[write_tail_q]<=incoming_write;
        write_tail_q<=write_tail_q+1'b1;
      end
      if(return_queued_write && rsp_ready[0]) queued_response_q<=0;
      for(int p=0;p<2;p++) begin
        if((response_valid_q[p] || forward_response[p]) && rsp_ready[p]) begin response_valid_q[p]<=0;busy_q[p]<=0;end
        if(accept[p] && !(p==0 && enqueue_write)) begin
          busy_q[p]<=1;response_id_q[p]<=req_id[p];response_valid_q[p]<=bad[p] || hit[p];
          response_code_q[p]<=bad[p] ? AXI_RESP_SLVERR:AXI_RESP_OKAY;
          if(bad[p]) response_data_q[p]<=0;
        end
      end
      // Exactly one synchronous read expression per bank, with tagged owner.
      if(bank_read_en[0]) response_data_q[bank_read_owner[0]]<=data_bank0[bank_read_row[0]];
      if(bank_read_en[1]) response_data_q[bank_read_owner[1]]<=data_bank1[bank_read_row[1]];
      if(|accept) turn_q<=accept[0] && accept[1] ? !turn_q:accept[0];
      if(state_q!=IDLE && invalidate_request) killed_q<=1;
      case(state_q)
        IDLE: if(launch_queued_write) begin
          queued_owner_q<=1;
          addr_q<=issued_write.address;
          id_q<=issued_write.id;
          write_q<=1;device_q<=0;committed_q<=1;cached_q<=1;filling_q<=0;
          size_q<=issued_write.size;
          wdata_q<=issued_write.data;
          wstrb_q<=issued_write.strobe;
          priv_q<=issued_write.privilege;
          seq_q<=issued_write.seq;
          state_q<=mem.req_ready ? WAIT_MEM:SEND;
        end else if(engine_accept) begin
          queued_owner_q<=0;
          owner_q<=engine_port;addr_q<=req_addr[engine_port];id_q<=req_id[engine_port];
          write_q<=req_write[engine_port];size_q<=req_size[engine_port];
          wdata_q<=req_wdata[engine_port];wstrb_q<=req_wstrb[engine_port];
          priv_q<=privilege_e'(req_priv[engine_port]);seq_q<=req_seq[engine_port];
          committed_q<=req_committed[engine_port];device_q<=req_device[engine_port];
          cached_q<=cacheable[engine_port];filling_q<=cacheable[engine_port] && !req_write[engine_port];
          killed_q<=0;beat_q<=0;selected_data_q<=0;
          if(cacheable[engine_port] && !req_write[engine_port]) valid_q[req_index[engine_port]]<=0;
          state_q<=mem.req_ready ? WAIT_MEM:SEND;
        end
        SEND: if(mem.req_valid && mem.req_ready) state_q<=WAIT_MEM;
        WAIT_MEM: if(mem.rsp_valid && mem.rsp_ready) begin
          if(queued_owner_q) begin
            queued_id_q<=id_q;queued_response_q<=busy_q[0] || !rsp_ready[0];
            queued_code_q<=axi_resp_e'(bus_response_code);
            write_head_q<=write_head_q+1'b1;state_q<=IDLE;
            if(bus_response_code!=AXI_RESP_OKAY && tags[index]==tag_value) valid_q[index]<=0;
          end else if(mem.rsp_resp!=AXI_RESP_OKAY || mem.rsp_replay!=MEM_REPLAY_NONE) begin
            response_data_q[owner_q]<=0;response_code_q[owner_q]<=mem.rsp_resp==AXI_RESP_OKAY ? AXI_RESP_SLVERR:mem.rsp_resp;
            response_valid_q[owner_q]<=filling_q || !rsp_ready[owner_q];state_q<=IDLE;
            if(cached_q && tags[index]==tag_value) valid_q[index]<=0;
          end else if(!filling_q) begin
            response_data_q[owner_q]<=mem.rsp_rdata;response_valid_q[owner_q]<=!rsp_ready[owner_q];state_q<=IDLE;
          end else begin
            if(beat_q==addr_q[5:3]) selected_data_q<=mem.rsp_rdata;
            if(beat_q==7) begin
              tags[index]<=tag_value;if(!killed_q && !invalidate_request) valid_q[index]<=1;
              response_data_q[owner_q]<=addr_q[5:3]==7 ? mem.rsp_rdata:selected_data_q;
              response_valid_q[owner_q]<=1;state_q<=IDLE;
            end else begin beat_q<=beat_q+1'b1;state_q<=SEND;end
          end
        end
        default:state_q<=IDLE;
      endcase
      if(READ_ONLY && snoop_resident) valid_q[snoop_index]<=0;
      if(invalidate_i) valid_q<=0;
    end
  end
  // Payload is never reset-cleared. Snoop acceptance is the physical SRAM write.
  always_ff @(posedge clk_i) if(rst_ni) begin
    if(snoop_update && !snoop_addr_i[3]) begin
      for(int b=0;b<8;b++) if(snoop_wstrb_i[b]) data_bank0[{snoop_index,snoop_addr_i[5:4]}][8*b+:8]<=snoop_wdata_i[8*b+:8];
    end else if(fill_write && !beat_q[0]) data_bank0[{index,beat_q[2:1]}]<=mem.rsp_rdata;
    if(snoop_update && snoop_addr_i[3]) begin
      for(int b=0;b<8;b++) if(snoop_wstrb_i[b]) data_bank1[{snoop_index,snoop_addr_i[5:4]}][8*b+:8]<=snoop_wdata_i[8*b+:8];
    end else if(fill_write && beat_q[0]) data_bank1[{index,beat_q[2:1]}]<=mem.rsp_rdata;
  end
  initial begin
    if(SIZE_KB<1 || LINES<2 || (LINES&(LINES-1))!=0) $fatal(1,"Invalid cache geometry");
    if(BASE_ADDR[5:0]!=0 || MEMORY_KB==0) $fatal(1,"Invalid cacheable region");
  end
endmodule

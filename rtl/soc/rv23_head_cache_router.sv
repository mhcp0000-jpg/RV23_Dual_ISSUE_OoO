// Transparent request arbitration; preserve the resident-hit pipeline latency.
module rv23_local_port_mux(
  input logic clk_i,rst_ni,
  output logic idle_o,
  rv_local_mem_if.target a,b,
  rv_local_mem_if.requester out_bus
);
  logic owner_q,outstanding_q,locked_q,selection_q,turn_q,choose,slot_free;
  assign choose=locked_q?selection_q:(b.req_valid && (!a.req_valid || turn_q));
  assign slot_free=!outstanding_q || (out_bus.rsp_valid && out_bus.rsp_ready);
  assign idle_o=!outstanding_q && !locked_q;
  assign out_bus.req_valid=rst_ni && slot_free && (choose?b.req_valid:a.req_valid);
  assign a.req_ready=rst_ni && slot_free && !choose && out_bus.req_ready;
  assign b.req_ready=rst_ni && slot_free && choose && out_bus.req_ready;
  assign out_bus.req_id=choose?b.req_id:a.req_id;
  assign out_bus.req_addr=choose?b.req_addr:a.req_addr;
  assign out_bus.req_write=choose?b.req_write:a.req_write;
  assign out_bus.req_size=choose?b.req_size:a.req_size;
  assign out_bus.req_wdata=choose?b.req_wdata:a.req_wdata;
  assign out_bus.req_wstrb=choose?b.req_wstrb:a.req_wstrb;
  assign out_bus.req_priv=choose?b.req_priv:a.req_priv;
  assign out_bus.req_rob_seq=choose?b.req_rob_seq:a.req_rob_seq;
  assign out_bus.req_committed=choose?b.req_committed:a.req_committed;
  assign out_bus.req_device=choose?b.req_device:a.req_device;
  assign out_bus.rsp_ready=outstanding_q && (owner_q?b.rsp_ready:a.rsp_ready);
  assign a.rsp_valid=outstanding_q && !owner_q && out_bus.rsp_valid;
  assign b.rsp_valid=outstanding_q && owner_q && out_bus.rsp_valid;
  assign a.rsp_id=out_bus.rsp_id;
  assign b.rsp_id=out_bus.rsp_id;
  assign a.rsp_rdata=out_bus.rsp_rdata;
  assign b.rsp_rdata=out_bus.rsp_rdata;
  assign a.rsp_resp=out_bus.rsp_resp;
  assign b.rsp_resp=out_bus.rsp_resp;
  assign a.rsp_replay=out_bus.rsp_replay;
  assign b.rsp_replay=out_bus.rsp_replay;
  always_ff @(posedge clk_i)begin
    if(!rst_ni)begin owner_q<=0;outstanding_q<=0;locked_q<=0;selection_q<=0;turn_q<=0;end
    else begin
      if(out_bus.rsp_valid && out_bus.rsp_ready)outstanding_q<=0;
      if(out_bus.req_valid)begin
        if(out_bus.req_ready)begin owner_q<=choose;outstanding_q<=1;locked_q<=0;turn_q<=!choose;end
        else begin locked_q<=1;selection_q<=choose;end
      end
    end
  end
endmodule

// Head accesses choose cache or maintenance bypass per accepted transaction.
module rv23_head_cache_router(
  input logic clk_i,rst_ni,head_cache_i,
  output logic idle_o,
  rv_local_mem_if.target scalar_bus,head_bus,
  rv_local_mem_if.requester cache_bus,direct_bus
);
  rv_local_mem_if cached_head(.clk_i,.rst_ni);
  logic busy_q,route_q,locked_q,locked_route_q,choose_cache,slot_free,mux_idle;
  assign choose_cache=locked_q?locked_route_q:head_cache_i;
  assign slot_free=!busy_q || (head_bus.rsp_valid && head_bus.rsp_ready);
  assign idle_o=mux_idle && !busy_q && !locked_q;
  rv23_local_port_mux u_cache_mux(.clk_i,.rst_ni,.idle_o(mux_idle),.a(scalar_bus),.b(cached_head),.out_bus(cache_bus));
  assign cached_head.req_valid=rst_ni && slot_free && choose_cache && head_bus.req_valid;
  assign direct_bus.req_valid=rst_ni && slot_free && !choose_cache && head_bus.req_valid;
  assign head_bus.req_ready=rst_ni && slot_free && (choose_cache?cached_head.req_ready:direct_bus.req_ready);
  assign cached_head.req_id=head_bus.req_id;
  assign direct_bus.req_id=head_bus.req_id;
  assign cached_head.req_addr=head_bus.req_addr;
  assign direct_bus.req_addr=head_bus.req_addr;
  assign cached_head.req_write=head_bus.req_write;
  assign direct_bus.req_write=head_bus.req_write;
  assign cached_head.req_size=head_bus.req_size;
  assign direct_bus.req_size=head_bus.req_size;
  assign cached_head.req_wdata=head_bus.req_wdata;
  assign direct_bus.req_wdata=head_bus.req_wdata;
  assign cached_head.req_wstrb=head_bus.req_wstrb;
  assign direct_bus.req_wstrb=head_bus.req_wstrb;
  assign cached_head.req_priv=head_bus.req_priv;
  assign direct_bus.req_priv=head_bus.req_priv;
  assign cached_head.req_rob_seq=head_bus.req_rob_seq;
  assign direct_bus.req_rob_seq=head_bus.req_rob_seq;
  assign cached_head.req_committed=head_bus.req_committed;
  assign direct_bus.req_committed=head_bus.req_committed;
  assign cached_head.req_device=head_bus.req_device;
  assign direct_bus.req_device=head_bus.req_device;
  assign cached_head.rsp_ready=busy_q && route_q && head_bus.rsp_ready;
  assign direct_bus.rsp_ready=busy_q && !route_q && head_bus.rsp_ready;
  assign head_bus.rsp_valid=busy_q && (route_q?cached_head.rsp_valid:direct_bus.rsp_valid);
  assign head_bus.rsp_id=route_q?cached_head.rsp_id:direct_bus.rsp_id;
  assign head_bus.rsp_rdata=route_q?cached_head.rsp_rdata:direct_bus.rsp_rdata;
  assign head_bus.rsp_resp=route_q?cached_head.rsp_resp:direct_bus.rsp_resp;
  assign head_bus.rsp_replay=route_q?cached_head.rsp_replay:direct_bus.rsp_replay;
  always_ff @(posedge clk_i)begin
    if(!rst_ni)begin busy_q<=0;route_q<=0;locked_q<=0;locked_route_q<=0;end
    else begin
      if(head_bus.rsp_valid && head_bus.rsp_ready)busy_q<=0;
      if(head_bus.req_valid)begin
        if(head_bus.req_ready)begin busy_q<=1;route_q<=choose_cache;locked_q<=0;end
        else begin locked_q<=1;locked_route_q<=choose_cache;end
      end
    end
  end
endmodule

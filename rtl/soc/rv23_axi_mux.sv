// Two masters share one AXI port. Read/write ownership lasts through the
// final response; address grant ownership also survives target backpressure.
module rv23_axi_mux(input logic clk_i,rst_ni,
  rv_axi4_if.slave a_s,b_s,rv_axi4_if.master out_m);
  logic write_busy_q,read_busy_q,write_owner_q,read_owner_q;
  logic aw_hold_q,ar_hold_q,aw_owner_q,ar_owner_q,aw_turn_q,ar_turn_q;
  logic aw_select,ar_select;
  assign aw_select=aw_hold_q?aw_owner_q:
    (a_s.aw_valid && b_s.aw_valid ? aw_turn_q:b_s.aw_valid);
  assign ar_select=ar_hold_q?ar_owner_q:
    (a_s.ar_valid && b_s.ar_valid ? ar_turn_q:b_s.ar_valid);
  always_comb begin
    out_m.aw_id=aw_select?b_s.aw_id:a_s.aw_id;
    out_m.aw_addr=aw_select?b_s.aw_addr:a_s.aw_addr;
    out_m.aw_len=aw_select?b_s.aw_len:a_s.aw_len;
    out_m.aw_size=aw_select?b_s.aw_size:a_s.aw_size;
    out_m.aw_burst=aw_select?b_s.aw_burst:a_s.aw_burst;
    out_m.aw_lock=aw_select?b_s.aw_lock:a_s.aw_lock;
    out_m.aw_prot=aw_select?b_s.aw_prot:a_s.aw_prot;
    out_m.aw_cache=aw_select?b_s.aw_cache:a_s.aw_cache;
    out_m.aw_qos=aw_select?b_s.aw_qos:a_s.aw_qos;
    out_m.aw_valid=!write_busy_q && (aw_select?b_s.aw_valid:a_s.aw_valid);
    a_s.aw_ready=!write_busy_q && !aw_select && out_m.aw_ready;
    b_s.aw_ready=!write_busy_q && aw_select && out_m.aw_ready;
    out_m.ar_id=ar_select?b_s.ar_id:a_s.ar_id;
    out_m.ar_addr=ar_select?b_s.ar_addr:a_s.ar_addr;
    out_m.ar_len=ar_select?b_s.ar_len:a_s.ar_len;
    out_m.ar_size=ar_select?b_s.ar_size:a_s.ar_size;
    out_m.ar_burst=ar_select?b_s.ar_burst:a_s.ar_burst;
    out_m.ar_lock=ar_select?b_s.ar_lock:a_s.ar_lock;
    out_m.ar_prot=ar_select?b_s.ar_prot:a_s.ar_prot;
    out_m.ar_cache=ar_select?b_s.ar_cache:a_s.ar_cache;
    out_m.ar_qos=ar_select?b_s.ar_qos:a_s.ar_qos;
    out_m.ar_valid=!read_busy_q && (ar_select?b_s.ar_valid:a_s.ar_valid);
    a_s.ar_ready=!read_busy_q && !ar_select && out_m.ar_ready;
    b_s.ar_ready=!read_busy_q && ar_select && out_m.ar_ready;
    out_m.w_data=write_owner_q?b_s.w_data:a_s.w_data;
    out_m.w_strb=write_owner_q?b_s.w_strb:a_s.w_strb;
    out_m.w_last=write_owner_q?b_s.w_last:a_s.w_last;
    out_m.w_valid=write_busy_q && (write_owner_q?b_s.w_valid:a_s.w_valid);
    a_s.w_ready=write_busy_q && !write_owner_q && out_m.w_ready;
    b_s.w_ready=write_busy_q && write_owner_q && out_m.w_ready;
    out_m.b_ready=write_busy_q && (write_owner_q?b_s.b_ready:a_s.b_ready);
    out_m.r_ready=read_busy_q && (read_owner_q?b_s.r_ready:a_s.r_ready);
    a_s.b_id=out_m.b_id;
    a_s.b_resp=out_m.b_resp;
    a_s.b_valid=write_busy_q && !write_owner_q && out_m.b_valid;
    b_s.b_id=out_m.b_id;
    b_s.b_resp=out_m.b_resp;
    b_s.b_valid=write_busy_q && write_owner_q && out_m.b_valid;
    a_s.r_id=out_m.r_id;
    a_s.r_data=out_m.r_data;
    a_s.r_resp=out_m.r_resp;
    a_s.r_last=out_m.r_last;
    a_s.r_valid=read_busy_q && !read_owner_q && out_m.r_valid;
    b_s.r_id=out_m.r_id;
    b_s.r_data=out_m.r_data;
    b_s.r_resp=out_m.r_resp;
    b_s.r_last=out_m.r_last;
    b_s.r_valid=read_busy_q && read_owner_q && out_m.r_valid;
  end
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      write_busy_q<=0;read_busy_q<=0;write_owner_q<=0;read_owner_q<=0;
      aw_hold_q<=0;ar_hold_q<=0;aw_owner_q<=0;ar_owner_q<=0;aw_turn_q<=0;ar_turn_q<=0;
    end else begin
      if(out_m.aw_valid && out_m.aw_ready) begin
        write_busy_q<=1;write_owner_q<=aw_select;aw_hold_q<=0;aw_turn_q<=!aw_select;
      end else if(out_m.aw_valid) begin aw_hold_q<=1;aw_owner_q<=aw_select;end
      if(out_m.b_valid && out_m.b_ready) write_busy_q<=0;
      if(out_m.ar_valid && out_m.ar_ready) begin
        read_busy_q<=1;read_owner_q<=ar_select;ar_hold_q<=0;ar_turn_q<=!ar_select;
      end else if(out_m.ar_valid) begin ar_hold_q<=1;ar_owner_q<=ar_select;end
      if(out_m.r_valid && out_m.r_ready && out_m.r_last) read_busy_q<=0;
    end
  end
endmodule

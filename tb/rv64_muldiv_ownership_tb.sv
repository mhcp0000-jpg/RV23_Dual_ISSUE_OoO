module rv64_muldiv_ownership_tb;
  import rv_ooo_pkg::*;
  logic clk=0,rst_n=0;
  always #5 clk=~clk;
  logic [1:0] req_v,req_r,res_v,res_r,word_op,dst_v,out_dst_v,fv,fa;
  logic [1:0][63:0] a,b,result;
  logic [1:0][7:0] seq_value,boundary,out_seq;
  logic [1:0][6:0] dst,out_dst;
  int cases_count=0,killed=0,preserved=0,reused=0,results=0,zero_dest=0;
  rv_multiplier #(.XLEN(64)) u_mul(.clk_i(clk),.rst_ni(rst_n),
    .request_valid_i(req_v[0]),.request_ready_o(req_r[0]),.operand_a_i(a[0]),.operand_b_i(b[0]),
    .operation_i(MUL_LOW),.word_operation_i(word_op[0]),.sequence_i(seq_value[0]),
    .destination_valid_i(dst_v[0]),.destination_phys_i(dst[0]),.flush_valid_i(fv[0]),
    .flush_all_i(fa[0]),.flush_sequence_i(boundary[0]),.result_valid_o(res_v[0]),
    .result_ready_i(res_r[0]),.result_o(result[0]),.result_sequence_o(out_seq[0]),
    .result_destination_valid_o(out_dst_v[0]),.result_destination_phys_o(out_dst[0]));
  rv_divider #(.XLEN(64)) u_div(.clk_i(clk),.rst_ni(rst_n),
    .request_valid_i(req_v[1]),.request_ready_o(req_r[1]),.operand_a_i(a[1]),.operand_b_i(b[1]),
    .operation_i(DIV_SIGNED_QUOTIENT),.word_operation_i(word_op[1]),.request_rob_sequence_i(seq_value[1]),
    .request_destination_valid_i(dst_v[1]),.request_destination_phys_i(dst[1]),.flush_valid_i(fv[1]),
    .flush_all_i(fa[1]),.flush_sequence_i(boundary[1]),.result_valid_o(res_v[1]),
    .result_ready_i(res_r[1]),.result_o(result[1]),.result_rob_sequence_o(out_seq[1]),
    .result_destination_valid_o(out_dst_v[1]),.result_destination_phys_o(out_dst[1]));
  task automatic send_request(input int unit_id,input bit word_value,input byte unsigned owner,
    input bit destination_valid,input logic [6:0] tag_value);
    @(negedge clk);
    a[unit_id]=word_value ? 64'hdeadbeef00000064:64'hf123456789abcdef;
    b[unit_id]=3;word_op[unit_id]=word_value;seq_value[unit_id]=owner;
    dst_v[unit_id]=destination_valid;dst[unit_id]=tag_value;req_v[unit_id]=1;
    while(!req_r[unit_id]) @(negedge clk);
    @(posedge clk);#1;
    @(negedge clk);req_v[unit_id]=0;
  endtask
  task automatic await_result(input int unit_id);
    int limit_count=0;
    while(!res_v[unit_id]) begin
      @(posedge clk);#1;limit_count++;
      if(limit_count>80)$fatal(1,"Missing result unit=%0d",unit_id);
    end
  endtask
  task automatic consume(input int unit_id,input bit word_value,input byte unsigned owner,
    input bit destination_valid,input logic [6:0] tag_value);
    logic [63:0] wanted;
    wanted=unit_id==0 ? (word_value ? 64'd300:64'hf123456789abcdef*64'd3):
      (word_value ? 64'd33:$unsigned($signed(64'hf123456789abcdef)/64'sd3));
    await_result(unit_id);
    repeat(4)begin
      @(negedge clk);
      if(!res_v[unit_id] || out_seq[unit_id]!==owner || out_dst_v[unit_id]!==destination_valid ||
         (destination_valid && (result[unit_id]!==wanted || out_dst[unit_id]!==tag_value)))
        $fatal(1,"Result ownership/backpressure mismatch unit=%0d",unit_id);
    end
    res_r[unit_id]=1;@(posedge clk);#1;
    @(negedge clk);res_r[unit_id]=0;
    if(res_v[unit_id])$fatal(1,"Duplicate consumed result");
    results++;
  endtask
  task automatic scenario(input int unit_id,input bit word_value,input byte unsigned owner,
    input byte unsigned cut,input bit held,input bit all_value,input bit must_kill);
    send_request(unit_id,word_value,owner,1,7'd17);
    if(held)begin await_result(unit_id);@(negedge clk);end
    else if((unit_id==0 && !u_mul.stage0_valid_q) || (unit_id==1 && !u_div.busy_q))
      $fatal(1,"Missing active request before flush");
    fv[unit_id]=1;fa[unit_id]=all_value;boundary[unit_id]=cut;
    req_v[unit_id]=1;
    #1;if(req_r[unit_id])$fatal(1,"Accepted request during flush");
    @(posedge clk);#1;
    @(negedge clk);fv[unit_id]=0;fa[unit_id]=0;req_v[unit_id]=0;
    if(must_kill)begin
      if(res_v[unit_id] || (unit_id==0 && u_mul.stage0_valid_q) || (unit_id==1 && u_div.busy_q))
        $fatal(1,"Killed owner survived flush");
      repeat(3)begin @(negedge clk);if(res_v[unit_id])$fatal(1,"Late killed result");end
      killed++;
      send_request(unit_id,word_value,8'd9,1,7'd29);
      consume(unit_id,word_value,8'd9,1,7'd29);reused++;
    end else begin consume(unit_id,word_value,owner,1,7'd17);preserved++;end
    cases_count++;
  endtask
  initial begin
    req_v=0;res_r=0;word_op=0;dst_v=0;fv=0;fa=0;a=0;b=0;seq_value=0;boundary=0;dst=0;
    repeat(4)@(negedge clk);rst_n=1;
    for(int unit_id=0;unit_id<2;unit_id++)for(int w=0;w<2;w++)begin
      scenario(unit_id,1'(w),8'd2,8'd250,0,0,1);
      scenario(unit_id,1'(w),8'd250,8'd2,0,0,0);
      scenario(unit_id,1'(w),8'd2,8'd250,1,0,1);
      scenario(unit_id,1'(w),8'd250,8'd250,1,0,0);
      scenario(unit_id,1'(w),8'd250,8'd2,1,1,1);
      send_request(unit_id,1'(w),8'd19,0,7'd37);
      consume(unit_id,1'(w),8'd19,0,7'd37);zero_dest++;
    end
    if(cases_count!=20 || killed!=12 || preserved!=8 || reused!=12 || results!=24 || zero_dest!=4)
      $fatal(1,"Missing ownership scenario");
    $display("MULDIV_OWNERSHIP cases=%0d killed=%0d preserved=%0d reused=%0d results=%0d zero_dest=%0d",
      cases_count,killed,preserved,reused,results,zero_dest);
    $display("PASS rv64_muldiv_ownership_tb");$finish;
  end
  initial begin #200000;$fatal(1,"Ownership watchdog");end
endmodule

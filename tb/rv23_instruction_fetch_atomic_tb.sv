`timescale 1ns/1ps
module rv23_instruction_fetch_atomic_tb;
  localparam logic [31:0] BASE = 32'h8000_0000;
  localparam logic [31:0] OLD = 32'h1230_0293; // addi x5,x0,0x123
  localparam logic [31:0] NEW = 32'h4560_0313; // addi x6,x0,0x456
  localparam logic [31:0] FENCE_I = 32'h0000_100f;
  logic clk_i=0, rst_ni=0, run=0, final_write_done=0;
  always #5 clk_i=~clk_i;
  rv_axi4_if #(.ID_WIDTH(4)) dbg (.clk_i,.rst_ni);
  logic [1:0] valid, trap;
  logic [1:0][63:0] pc;
  logic [1:0][31:0] instruction;
  logic [31:0] target=BASE;
  int old_count=0, new_count=0, overlapping_writes=0;
  int total_overlaps=0;
  bit fenced_after_final=0, saw_final=0;

  rv23_soc_top dut (
    .clk_i,.rst_ni,.core_run_i(run),.external_irq_i('0),
    .debug_halt_req_i(1'b0),.debug_axi_s(dbg),.host_event_ready_i(1'b1),
    .trace_valid_o(valid),.trace_trap_o(trap),.trace_pc_o(pc),.trace_instr_o(instruction));

  task automatic write_word(input logic [31:0] address, word);
    @(negedge clk_i);
    dbg.aw_addr=address; dbg.aw_valid=1;
    do @(posedge clk_i); while (!dbg.aw_ready);
    @(negedge clk_i);
    dbg.aw_valid=0;
    dbg.w_data={32'b0,word} << (address[2]*32);
    dbg.w_strb=8'h0f << (address[2]*4);
    dbg.w_valid=1;
    do @(posedge clk_i); while (!dbg.w_ready);
    @(negedge clk_i); dbg.w_valid=0;
    do @(posedge clk_i); while (!dbg.b_valid);
    if (dbg.b_resp != 0) $fatal(1,"Debug AXI write failed addr=%h",address);
    @(negedge clk_i);
  endtask

  function automatic logic [31:0] jump(input logic [20:0] offset);
    return {offset[20],offset[10:1],offset[11],offset[19:12],5'd0,7'h6f};
  endfunction

  wire target_refill = dut.u_icache.state_q != 2'd0 &&
                       dut.u_icache.filling_q && dut.u_icache.addr_q[31:6] == target[31:6];

  always @(posedge clk_i) if (rst_ni && run) begin
    if (dut.sram_write_snoop && target_refill)
      overlapping_writes++;
    for (int lane=0;lane<2;lane++) if (valid[lane]) begin
      if (trap[lane]) $fatal(1,"Unexpected trap pc=%h",pc[lane]);
      if (pc[lane]==64'(target)) begin
        case (instruction[lane])
          OLD: old_count++;
          NEW: new_count++;
          default: $fatal(1,"Torn aligned 32-bit instruction %h",instruction[lane]);
        endcase
        if (fenced_after_final) begin
          if (instruction[lane]!=NEW) $fatal(1,"Stale instruction after FENCE.I");
          saw_final=1;
        end
      end
      if (final_write_done && instruction[lane]==FENCE_I) fenced_after_final=1;
    end
  end

  task automatic test_word(input int offset);
    @(negedge clk_i);
    rst_ni=0;run=0;final_write_done=0;fenced_after_final=0;saw_final=0;
    old_count=0;new_count=0;overlapping_writes=0;target=BASE+32'(offset);
    repeat(4) @(negedge clk_i); rst_ni=1;
    if (offset!=0) write_word(BASE,jump(21'(offset)));
    write_word(target,OLD);
    write_word(target+4,FENCE_I);
    write_word(target+8,jump(-21'd8));
    run=1;
    wait(old_count!=0);
    for (int index=0;index<31;index++) begin
      wait(target_refill);
      repeat(index%9) @(negedge clk_i);
      write_word(target,index[0] ? OLD : NEW);
    end
    final_write_done=1;
    wait(saw_final);
    if (overlapping_writes==0 || new_count==0)
      $fatal(1,"Missing fetch/write overlap coverage at offset %0d",offset);
    total_overlaps+=overlapping_writes;
    $display("IFETCH_ATOMIC offset=%0d old=%0d new=%0d refill_overlaps=%0d",
             offset,old_count,new_count,overlapping_writes);
  endtask

  initial begin
    dbg.aw_id=0;dbg.aw_addr=0;dbg.aw_len=0;dbg.aw_size=2;dbg.aw_burst=1;
    dbg.aw_lock=0;dbg.aw_prot=1;dbg.aw_cache=0;dbg.aw_qos=0;dbg.aw_valid=0;
    dbg.w_data=0;dbg.w_strb=0;dbg.w_last=1;dbg.w_valid=0;dbg.b_ready=1;
    dbg.ar_id=0;dbg.ar_addr=0;dbg.ar_len=0;dbg.ar_size=3;dbg.ar_burst=1;
    dbg.ar_lock=0;dbg.ar_prot=1;dbg.ar_cache=0;dbg.ar_qos=0;dbg.ar_valid=0;dbg.r_ready=1;
    for (int offset=0;offset<64;offset+=4) test_word(offset);
    $display("PASS rv23_instruction_fetch_atomic_tb offsets=16 refill_overlaps=%0d",total_overlaps);
    $finish;
  end
  initial begin #2000000; $fatal(1,"Instruction fetch atomicity watchdog"); end
endmodule

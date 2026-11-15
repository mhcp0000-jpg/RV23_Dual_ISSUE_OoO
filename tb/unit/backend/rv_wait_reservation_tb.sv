`timescale 1ns/1ps
module rv_wait_reservation_tb;
  logic clk_i=0,rst_ni=0;
  always #5 clk_i=~clk_i;
  logic valid=0,short_wait=0,reserved=0,irq=0,debug_wake=0,tw=0,virt=0,vtw=0;
  logic [1:0] priv=3;
  logic done,exception_flag;
  logic [5:0] cause;
  rv23_wait_reservation #(.SHORT_CYCLES(8),.TRAP_CYCLES(16)) dut(
    .clk_i,.rst_ni,.request_valid_i(valid),.short_timeout_i(short_wait),
    .reservation_valid_i(reserved),.interrupt_wake_i(irq),.debug_wake_i(debug_wake),
    .privilege_i(priv),.tw_i(tw),.virtual_i(virt),.vtw_i(vtw),
    .completion_valid_o(done),.exception_o(exception_flag),.cause_o(cause));
  task automatic restart;
    @(negedge clk_i);valid=0;@(negedge clk_i);valid=1;
  endtask
  initial begin
    repeat(3) @(negedge clk_i);rst_ni=1;valid=1;
    #1;if(!done || exception_flag)$fatal(1,"empty reservation must resume");
    reserved=1;short_wait=1;restart();
    repeat(6) begin @(negedge clk_i);if(done)$fatal(1,"short timeout too early");end
    @(negedge clk_i);if(!done || exception_flag)$fatal(1,"short timeout absent");
    short_wait=0;restart();
    repeat(30) begin @(negedge clk_i);if(done)$fatal(1,"NTO falsely timed out");end
    irq=1;#1;if(!done || exception_flag)$fatal(1,"locally enabled interrupt did not wake");
    irq=0;restart();debug_wake=1;#1;if(!done)$fatal(1,"debug drain did not wake");
    debug_wake=0;restart();reserved=0;#1;if(!done)$fatal(1,"reservation snoop did not wake");
    reserved=1;priv=1;tw=1;restart();
    repeat(14) begin @(negedge clk_i);if(done)$fatal(1,"TW trapped too early");end
    @(negedge clk_i);if(!done || !exception_flag || cause!=2)$fatal(1,"TW illegal trap missing");
    // STO is usable with TW and never takes its NTO privilege timeout trap.
    short_wait=1;restart();repeat(7) @(negedge clk_i);
    if(!done || exception_flag)$fatal(1,"STO incorrectly trapped with TW");
    short_wait=0;tw=0;virt=1;vtw=1;restart();repeat(15) @(negedge clk_i);
    if(!done || !exception_flag || cause!=22)$fatal(1,"VTW virtual trap missing");
    $display("PASS rv_wait_reservation_tb timeout, interrupt, snoop, debug, TW/VTW");$finish;
  end
  initial begin #10000;$fatal(1,"WRS timeout");end
endmodule

`timescale 1ns/1ps
// Observes the production core without driving its requests, clocks or state.
module rv23_vector_performance_tb;
  rv32_program_tb #(.XLEN(64),.HAS_V(1),.HAS_H(1),.HAS_MISALIGNED(1),
    .HAS_D(1),.HAS_ZFHMIN(1),.HAS_ZFA(1),.HAS_ZAWRS(1),.HAS_ZIMOP(1),
    .HAS_ZCMOP(1),.HAS_ZCB(1),.HAS_SVINVAL(1),.HAS_SSNPM(1),.HAS_CBO(1),
    .HAS_A(1),.HAS_B(1),.HAS_ZICOND(1),.HAS_SMODE(1),.HAS_MMU(1)) core();
`define V core.u_dut.u_core.u_backend.g_vector_head.u_head
  logic [63:0] start_pc,stop_pc;
  bit active=0,started=0,stopped=0,pending=0;
  longint unsigned cycles=0,retired=0,no_retire=0,requests=0,responses=0;
  longint unsigned request_cycle=0,memory_latency=0,memory_max=0;
  longint unsigned states[16]='{default:0},empty_states[16]='{default:0};
  longint unsigned memory_states[8]='{default:0};
  longint unsigned hits=0,misses=0,request_stalls=0,response_wait=0;
  initial begin
    if(!$value$plusargs("profile_start_pc=%h",start_pc) ||
       !$value$plusargs("profile_stop_pc=%h",stop_pc))
      $fatal(1,"Performance window PCs are required");
  end
  always @(posedge core.clk)if(core.rst_n && core.load_done)begin
    for(int p=0;p<2;p++)if(core.trace_valid[p] && !core.trace_trap[p])begin
      if(core.trace_pc[p]==start_pc)begin
        if(started)$fatal(1,"Repeated performance window");
        started=1;active=1;
      end
      if(core.trace_pc[p]==stop_pc)begin
        if(!active)$fatal(1,"Stop without start");
        active=0;stopped=1;
      end
    end
    if(active)begin
      cycles++;retired+=$countones(core.trace_valid);
      states[int'(`V.state_q)]++;
      if(core.trace_valid==0)begin no_retire++;empty_states[int'(`V.state_q)]++;end
      if(`V.state_q==`V.MEM_WAIT)memory_states[int'(`V.u_memory.state_q)]++;
      hits+=$countones(core.u_dut.u_dcache.hit_accept);
      misses+=$countones(core.u_dut.u_dcache.miss_accept);
      if(`V.memory_valid_o && !`V.memory_ready_i)request_stalls++;
      if(pending && !`V.memory_response_valid_i)response_wait++;
      if(`V.memory_response_valid_i && `V.memory_response_ready_o)begin
        if(!pending)$fatal(1,"Memory response without pending request");
        responses++;memory_latency+=cycles-request_cycle;
        if(cycles-request_cycle>memory_max)memory_max=cycles-request_cycle;
        pending=0;
      end
      if(`V.memory_valid_o && `V.memory_ready_i)begin
        if(pending)$fatal(1,"Unexpected multiple vector memory requests");
        requests++;pending=1;request_cycle=cycles;
      end
    end
  end
  final begin
    if(!started || !stopped || pending)$error("Incomplete performance window");
    $display("VECTOR_PROFILE cycles=%0d retired=%0d empty=%0d requests=%0d responses=%0d latency_sum=%0d latency_max=%0d hits=%0d misses=%0d request_stalls=%0d response_wait=%0d",
      cycles,retired,no_retire,requests,responses,memory_latency,memory_max,hits,misses,request_stalls,response_wait);
    for(int s=0;s<16;s++)$display("VECTOR_PROFILE_STATE index=%0d cycles=%0d empty=%0d",s,states[s],empty_states[s]);
    for(int s=0;s<8;s++)$display("VECTOR_PROFILE_MEMORY index=%0d cycles=%0d",s,memory_states[s]);
  end
`undef V
endmodule

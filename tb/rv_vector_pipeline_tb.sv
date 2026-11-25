module rv_vector_pipeline_tb;
  import rv_vector_decode_pkg::*;
  rv_vector_integer_engine_tb core();
  int add_run=0,write_run=0,max_add=0,max_write=0,issues=0,writes=0;
  int runs[4]='{default:0},max_runs[4]='{default:0},parallel[4]='{default:0};
  int packed_run=0,max_packed=0;
  int extension_run=0,max_extension_run=0,extension_issues=0,extension_parallel=0;
  always @(posedge core.clk)if(core.rst_n)begin
    if(core.dut.int_valid_q)issues++;
    if(core.dut.int_valid_q && (core.dut.int_operation_q inside {VI_VZEXT,VI_VSEXT}))begin
      if(!core.dut.int_meta_q.packed_mode)$fatal(1,"Extension bypassed packed lanes");
      extension_run++;extension_issues++;
      if($countones(core.dut.int_meta_q.active_mask)>extension_parallel)
        extension_parallel=$countones(core.dut.int_meta_q.active_mask);
    end else extension_run=0;
    if(extension_run>max_extension_run)max_extension_run=extension_run;
    if(core.dut.int_valid_q && core.dut.int_operation_q==VI_VADD)add_run++;
    else add_run=0;
    if(core.dut.rf_write_q)begin write_run++;writes++;end
    else write_run=0;
    if(add_run>max_add)max_add=add_run;
    if(write_run>max_write)max_write=write_run;
    for(int size=0;size<4;size++)begin
      if(core.dut.int_valid_q && core.dut.int_operation_q==VI_VADD && core.dut.int_meta_q.sew==size)begin
        runs[size]++;
        if($countones(core.dut.int_meta_q.active_mask)>parallel[size])parallel[size]=$countones(core.dut.int_meta_q.active_mask);
      end else runs[size]=0;
      if(runs[size]>max_runs[size])max_runs[size]=runs[size];
    end
    if(core.dut.rf_write_q && core.dut.rf_packed_q && (&core.dut.rf_bit_mask_q))packed_run++;
    else packed_run=0;
    if(packed_run>max_packed)max_packed=packed_run;
    if(core.response && (core.dut.int_valid_q || core.dut.int_result_valid_q || core.dut.rf_write_q))
      $fatal(1,"Vector completed before its pipeline drained");
  end
  final begin
    if(max_add<8 || max_write<8 || issues<64 || max_packed<8)$fatal(1,"Missing consecutive vector pipeline witness");
    if(max_extension_run<8 || extension_parallel<8)$fatal(1,"Missing extension batching witness");
    for(int size=0;size<4;size++)if(max_runs[size]<8 || parallel[size]!=(16>>size))$fatal(1,"Missing packed SEW witness %0d",size);
    $display("VECTOR_PIPELINE issues=%0d writes=%0d max_add=%0d max_write=%0d",issues,writes,max_add,max_write);
    $display("VECTOR_SIMD parallel=%0d/%0d/%0d/%0d batches=%0d/%0d/%0d/%0d full_writes=%0d",
      parallel[0],parallel[1],parallel[2],parallel[3],max_runs[0],max_runs[1],max_runs[2],max_runs[3],max_packed);
    $display("VECTOR_EXT issues=%0d max_run=%0d parallel=%0d",extension_issues,max_extension_run,extension_parallel);
  end
endmodule

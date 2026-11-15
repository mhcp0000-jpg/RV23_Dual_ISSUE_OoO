`timescale 1ns/1ps
module rv_vector_decode_tb #(
  parameter int COUNT=1,
  parameter string FILE=""
);
  import rv_vector_decode_pkg::*;
  logic [95:0] vectors[COUNT];
  vector_decode_t decoded;
  logic [15:0] metadata;
  initial begin
    $readmemh(FILE,vectors);
    for(int i=0;i<COUNT;i++) for(int extension_enabled=0;extension_enabled<2;extension_enabled++) begin
      decoded=decode_vector(vectors[i][95:64],1'(extension_enabled));
      metadata={7'b0,decoded.scalar_destination_fp,decoded.scalar_destination,
        decoded.scalar_source_fp[0],decoded.scalar_source_used[1:0],decoded.fp_operation,
        decoded.store,decoded.memory,decoded.configuration};
      if(decoded.valid!==(extension_enabled || vectors[i][0]==0) ||
         decoded.operation!==vector_operation_e'(vectors[i][63:48]) || metadata!==vectors[i][47:32])
        $fatal(1,"vector decode case%0d insn%h id%0d want%0d meta%h want%h valid%0d ext%0d",
          i,vectors[i][95:64],decoded.operation,vectors[i][63:48],metadata,vectors[i][47:32],decoded.valid,extension_enabled);
    end
    decoded=decode_vector(32'b0);if(decoded.valid)$fatal(1,"invalid zero instruction accepted");
    decoded=decode_vector(32'hffffffff);if(decoded.valid)$fatal(1,"reserved all-ones instruction accepted");
    $display("PASS rv_vector_decode_tb GNU vectors=%0d",COUNT);$finish;
  end
endmodule

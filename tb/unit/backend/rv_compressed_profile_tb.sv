`timescale 1ns/1ps
module rv_compressed_profile_tb #(
  parameter int XLEN=64,
  parameter bit HAS_D=0,
  parameter int CASES=1,
  parameter string VECTOR_FILE=""
);
  logic [15:0] compressed;
  logic [31:0] expanded,legacy;
  logic illegal,legacy_illegal;
  logic [47:0] vectors[CASES];
  bit known[65536];
  int additions=0;
  rv_c_expander #(.XLEN(XLEN),.HAS_D(HAS_D),.HAS_B(!HAS_D),.HAS_ZCB(!HAS_D),.HAS_ZCMOP(!HAS_D)) dut(
    .compressed_i(compressed),.instruction_o(expanded),.illegal_o(illegal));
  rv_c_expander #(.XLEN(XLEN)) baseline(
    .compressed_i(compressed),.instruction_o(legacy),.illegal_o(legacy_illegal));
  initial begin
    $readmemh(VECTOR_FILE,vectors);
    for(int i=0;i<CASES;i++) begin
      compressed=vectors[i][15:0];known[compressed]=1;#1;
      if(illegal || expanded!==vectors[i][47:16] || !legacy_illegal)
        $fatal(1,"RV%0d compressed %h got %h/%0d expected %h legacy illegal%0d",
          XLEN,compressed,expanded,illegal,vectors[i][47:16],legacy_illegal);
    end
    for(int i=0;i<65536;i++) begin
      compressed=16'(i);#1;
      if(legacy_illegal && !illegal) begin
        if(!known[i])$fatal(1,"unlisted reserved encoding became legal: %h",compressed);
        additions++;
      end else if(!legacy_illegal && (illegal || expanded!==legacy))
        $fatal(1,"existing compressed encoding changed: %h",compressed);
    end
    $display("PASS rv_compressed_profile_tb RV%0d vectors=%0d new_encodings=%0d",XLEN,CASES,additions);$finish;
  end
endmodule

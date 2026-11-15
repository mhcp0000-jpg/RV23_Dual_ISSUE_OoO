`timescale 1ns/1ps
module rv_bitmanip_tb #(parameter int unsigned XLEN=64);
  import rv_ooo_pkg::*;
  logic [255:0] vectors[0:32767];
  string vector_file;
  int count,checks=0;
  logic [1:0][31:0] instruction;
  logic [1:0][XLEN-1:0] pc='0;
  inst_len_e [1:0] length={INST_LEN_32,INST_LEN_32};
  prediction_meta_t [1:0] prediction='0;
  logic [1:0] valid,illegal,legacy_illegal;
  logic [1:0][15:0] operation;
  logic [1:0] word_op,use_imm;
  logic [1:0][XLEN-1:0] immediate,tval;
  logic [1:0][2:0] src_used;
  logic [XLEN-1:0] a,b,result;
  logic [31:0] flags;
  fu_class_e [1:0] fu;
  logic [1:0][4:0] port_mask;
  logic [1:0] writes;
  rv_decode2 #(.XLEN(XLEN),.HAS_B(1),.HAS_ZICOND(1)) dut (
    .in_valid_i(2'b11),.in_ready_o(),.in_pc_i(pc),.in_instruction_i(instruction),
    .in_inst_len_i(length),.in_prediction_i(prediction),.in_fetch_fault_i(2'b00),
    .fp_state_enabled_i(1'b1),.uop_valid_o(valid),.uop_ready_i(2'b11),
    .uop_operation_o(operation),.uop_word_operation_o(word_op),
    .uop_use_immediate_o(use_imm),.uop_immediate_o(immediate),.uop_src_used_o(src_used),
    .uop_exception_valid_o(illegal),.uop_exception_tval_o(tval),
    .uop_fu_o(fu),.uop_exec_port_mask_o(port_mask),.uop_writes_dst_o(writes));
  rv_decode2 #(.XLEN(XLEN),.HAS_B(0),.HAS_ZICOND(0)) legacy (
    .in_valid_i(2'b11),.in_ready_o(),.in_pc_i(pc),.in_instruction_i(instruction),
    .in_inst_len_i(length),.in_prediction_i(prediction),.in_fetch_fault_i(2'b00),
    .fp_state_enabled_i(1'b1),.uop_ready_i(2'b11),.uop_exception_valid_o(legacy_illegal));
  rv_int_alu #(.XLEN(XLEN)) alu (
    .operand_a_i(a),.operand_b_i(use_imm[0] ? immediate[0]:b),
    .operation_i(int_alu_op_e'(operation[0][5:0])),.word_operation_i(word_op[0]),.result_o(result));
  initial begin
    if(!$value$plusargs("vectors=%s",vector_file) || !$value$plusargs("count=%d",count))
      $fatal(1,"Missing bitmanip vectors/count");
    $readmemh(vector_file,vectors);
    for(int i=0;i<count;i++) begin
      instruction={vectors[i][255:224],vectors[i][255:224]};
      a=XLEN'(vectors[i][223:160]);b=XLEN'(vectors[i][159:96]);flags=vectors[i][31:0];
      #1;
      if(illegal!=={2{flags[0]}} || valid!==2'b11 || legacy_illegal!==2'b11)
        $fatal(1,"B decode/disabled/reserved mismatch vector=%0d insn=%h illegal=%b",i,instruction[0],illegal);
      if(!flags[0]) begin
        if(result!==XLEN'(vectors[i][95:32]) || operation[0]!==operation[1] ||
           fu[0]!=FU_INT || fu[1]!=FU_INT || !(&writes) ||
           !src_used[0][0] || port_mask[0]!==5'b00011)
          $fatal(1,"B execute/route mismatch vector=%0d insn=%h a=%h b=%h got=%h expected=%h",
            i,instruction[0],a,b,result,XLEN'(vectors[i][95:32]));
      end else if(writes!=0 || port_mask!=0 || tval[0]!==XLEN'(instruction[0]))
        $fatal(1,"Reserved B encoding had side effects");
      checks++;
    end
    $display("PASS rv_bitmanip_tb XLEN=%0d checks=%0d decode/execute/disabled/reserved",XLEN,checks);
    $finish;
  end
endmodule

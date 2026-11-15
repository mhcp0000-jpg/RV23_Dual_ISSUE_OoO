// SPDX-License-Identifier: Apache-2.0
module rv_fetch_fault_decode_case #(parameter int XLEN=64)(output logic done=0);
  import rv_ooo_pkg::*;
  logic [1:0][XLEN-1:0] pc,address,tval;
  logic [1:0][31:0] instruction;
  logic [1:0][5:0] cause;
  logic [1:0] fault,valid,writes_dst,is_load,is_store,is_branch,is_csr,is_fence,is_fence_i,serializing,exception;
  logic [1:0][4:0] ports;
  inst_len_e [1:0] length;
  fu_class_e [1:0] fu;
  exception_code_e [1:0] out_cause;
  logic [31:0] words[16]='{32'h002081b3,32'h00832283,32'h00532623,32'h00208463,
    32'h000780e7,32'h300110f3,32'h0000100f,32'h00208153,
    32'h022081b3,32'h0220c1b3,32'h00000073,32'hffffffff,
    32'h00009782,32'h00004000,32'h0000c000,32'h00000001};
  rv_decode2 #(.XLEN(XLEN),.HAS_D(1),.HAS_H(XLEN==64),.FETCH_FAULT_METADATA(1)) dut(
    .in_valid_i(2'b11),.in_ready_o(),.in_pc_i(pc),.in_instruction_i(instruction),
    .in_inst_len_i(length),.in_prediction_i('0),.in_fetch_fault_i(fault),
    .in_fetch_fault_cause_i(cause),.in_fetch_fault_address_i(address),
    .fp_state_enabled_i(1'b1),.uop_ready_i(2'b11),.uop_valid_o(valid),
    .uop_fu_o(fu),.uop_exec_port_mask_o(ports),.uop_writes_dst_o(writes_dst),
    .uop_is_load_o(is_load),.uop_is_store_o(is_store),.uop_is_branch_o(is_branch),
    .uop_is_csr_o(is_csr),.uop_is_fence_o(is_fence),.uop_is_fence_i_o(is_fence_i),
    .uop_is_serializing_o(serializing),.uop_exception_valid_o(exception),
    .uop_exception_cause_o(out_cause),.uop_exception_tval_o(tval));
  initial begin
    pc[0]=XLEN'(64'hffff_ffc0_80000ffe);pc[1]=pc[0]+4;
    address[0]=pc[0]+2;address[1]=pc[1];
    for(int kind=0;kind<3;kind++) begin
      cause='{default:6'(kind==0?1:kind==1?12:20)};
      for(int op=0;op<16;op++) for(int mask=1;mask<4;mask++) begin
        instruction[0]=words[op];instruction[1]=words[op];
        length='{default:op<12?INST_LEN_32:INST_LEN_16};fault=2'(mask);
        #1;
        for(int lane=0;lane<2;lane++) if(fault[lane]) begin
          assert(valid[lane] && exception[lane] && out_cause[lane]==exception_code_e'(cause[lane]) &&
                 tval[lane]==address[lane]) else $fatal(1,"fetch fault metadata XLEN=%0d op=%0d lane=%0d",XLEN,op,lane);
          assert(fu[lane]==FU_NONE && ports[lane]==0 && !writes_dst[lane] &&
                 !is_load[lane] && !is_store[lane] && !is_branch[lane] &&
                 !is_csr[lane] && !is_fence[lane] && !is_fence_i[lane] && !serializing[lane])
            else $fatal(1,"fetch fault entered execution XLEN=%0d op=%0d lane=%0d",XLEN,op,lane);
        end
      end
    end
    $display("PASS fetch fault decode XLEN=%0d 144 bundles/192 faulted lanes",XLEN);
    done=1;
  end
endmodule

module rv_fetch_fault_decode_tb;
  logic done32,done64;
  rv_fetch_fault_decode_case #(.XLEN(32)) rv32(done32);
  rv_fetch_fault_decode_case #(.XLEN(64)) rv64(done64);
  initial begin
    wait(done32 && done64);
    $display("PASS rv_fetch_fault_decode_tb 384 faulted lanes");$finish;
  end
endmodule

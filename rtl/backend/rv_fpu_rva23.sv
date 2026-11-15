// RV64 FLEN=64 F/D + Zfhmin + Zfa issue/result unit. Arithmetic is real RTL;
// backend metadata, NaN boxing and killed-operation ownership stay explicit.
module rv_fpu_rva23 #(
  parameter int unsigned XLEN=64,ROB_SEQ_WIDTH=rv_ooo_pkg::ROB_SEQ_WIDTH,PHYS_TAG_WIDTH=7,
  parameter bit HAS_D=1,HAS_ZFHMIN=1,HAS_ZFA=1
)(
  input logic clk_i,rst_ni,request_valid_i,
  output logic request_ready_o,
  input logic [31:0] instruction_i,
  input logic [XLEN-1:0] operand_a_i,operand_b_i,operand_c_i,
  input logic [2:0] rounding_mode_i,frm_i,
  input logic [ROB_SEQ_WIDTH-1:0] sequence_i,
  input logic destination_valid_i,
  input rv_ooo_pkg::reg_class_e destination_class_i,
  input logic [PHYS_TAG_WIDTH-1:0] destination_phys_i,
  input logic flush_valid_i,flush_all_i,
  input logic [ROB_SEQ_WIDTH-1:0] flush_sequence_i,
  output logic result_valid_o,
  input logic result_ready_i,
  output logic [ROB_SEQ_WIDTH-1:0] result_sequence_o,
  output logic result_destination_valid_o,
  output rv_ooo_pkg::reg_class_e result_destination_class_o,
  output logic [PHYS_TAG_WIDTH-1:0] result_destination_phys_o,
  output logic [XLEN-1:0] result_data_o,
  output logic [4:0] result_fflags_o,
  output logic result_exception_valid_o,
  output rv_ooo_pkg::exception_code_e result_exception_cause_o,
  output logic [XLEN-1:0] result_exception_tval_o
);
  import rv_ooo_pkg::*;
  import rv_fp_decode_pkg::*;
  typedef enum logic[1:0] {IDLE,EXECUTE,SLOW,RESULT} state_t;
  state_t state_q;
  logic [31:0] instruction_q;
  logic [63:0] a_q,b_q,c_q,data_q,a_s,b_s,c_s,a_d,b_d,c_d;
  logic [2:0] rounding_q;
  logic [ROB_SEQ_WIDTH-1:0] sequence_q;
  logic destination_valid_q,exception_q;
  reg_class_e destination_class_q;
  logic [PHYS_TAG_WIDTH-1:0] destination_phys_q;
  logic [4:0] flags_q,flags_s,flags_d,slow_flags_s,slow_flags_d;
  logic [63:0] data_s,data_d,converted,modular,round_d,fli_d;
  logic [31:0] slow_data_s,round_s,fli_s;
  logic [63:0] slow_data_d;
  logic [4:0] conversion_flags,round_flags_s,round_flags_d;
  logic fast_s,fast_d,slow_ready_s,slow_ready_d,slow_valid_s,slow_valid_d;
  logic kill,slow_operation,selected_slow_ready,selected_slow_valid;
  logic [63:0] selected_data;
  logic [4:0] selected_flags;
  logic selected_supported,integer_source,raw_move;
  logic [1:0] fmt;
  fp_decode_t decoded;
  function automatic logic [63:0] unbox(input logic [63:0] value,input logic[1:0] format_id);
    case(format_id)
      0:return (&value[63:32])?value:64'hffffffff7fc00000;
      2:return (&value[63:16])?value:64'hffffffffffff7e00;
      default:return value;
    endcase
  endfunction
  function automatic logic [63:0] box(input logic [63:0] value,input logic[1:0] format_id);
    case(format_id)
      0:return {32'hffffffff,value[31:0]};
      2:return {48'hffffffffffff,value[15:0]};
      default:return value;
    endcase
  endfunction
  function automatic logic younger(input logic [ROB_SEQ_WIDTH-1:0] x,y);
    logic signed [ROB_SEQ_WIDTH-1:0] delta;
    delta=$signed(x-y);return delta>0;
  endfunction
  assign kill=flush_valid_i && (flush_all_i || younger(sequence_q,flush_sequence_i));
  assign request_ready_o=rst_ni && !flush_valid_i && state_q==IDLE;
  assign result_valid_o=rst_ni && state_q==RESULT && !kill;
  assign result_sequence_o=sequence_q;
  assign result_destination_valid_o=destination_valid_q;
  assign result_destination_class_o=destination_class_q;
  assign result_destination_phys_o=destination_phys_q;
  assign result_data_o=XLEN'(data_q);assign result_fflags_o=flags_q;
  assign result_exception_valid_o=exception_q;
  assign result_exception_cause_o=EXC_ILLEGAL_INSTRUCTION;
  assign result_exception_tval_o=exception_q?XLEN'(instruction_q):'0;
  assign fmt=instruction_q[26:25];
  assign decoded=decode_fp(instruction_q,XLEN,HAS_D,HAS_ZFHMIN,HAS_ZFA);
  assign integer_source=instruction_q[6:0]==7'h53 &&
    (instruction_q[31:27]==26 || (instruction_q[31:27]==30 && instruction_q[24:20]==0));
  assign raw_move=instruction_q[6:0]==7'h53 && instruction_q[31:27]==28 && instruction_q[14:12]==0;
  assign a_s=(integer_source || raw_move)?a_q:unbox(a_q,0);
  assign b_s=unbox(b_q,0);assign c_s=unbox(c_q,0);
  assign a_d=a_q;assign b_d=b_q;assign c_d=c_q;
  assign slow_operation=instruction_q[6:0]==7'h53 &&
    (instruction_q[31:27]==3 || instruction_q[31:27]==11);
  assign selected_slow_ready=fmt==0?slow_ready_s:slow_ready_d;
  assign selected_slow_valid=fmt==0?slow_valid_s:slow_valid_d;
  rv_fp_format #(.EXP(8),.SIG(24)) u_single(
    .clk_i,.rst_ni(rst_ni && !kill),.instruction_i(instruction_q),.a_i(a_s),.b_i(b_s),.c_i(c_s),
    .rounding_i(rounding_q),.fast_data_o(data_s),.fast_flags_o(flags_s),.fast_supported_o(fast_s),
    .slow_valid_i(state_q==EXECUTE && decoded.valid && slow_operation && fmt==0 && !kill && rounding_q<=4),
    .slow_ready_o(slow_ready_s),.slow_result_valid_o(slow_valid_s),.slow_data_o(slow_data_s),.slow_flags_o(slow_flags_s));
  rv_fp_format u_double(
    .clk_i,.rst_ni(rst_ni && !kill),.instruction_i(instruction_q),.a_i(a_d),.b_i(b_d),.c_i(c_d),
    .rounding_i(rounding_q),.fast_data_o(data_d),.fast_flags_o(flags_d),.fast_supported_o(fast_d),
    .slow_valid_i(state_q==EXECUTE && decoded.valid && slow_operation && fmt==1 && !kill && rounding_q<=4),
    .slow_ready_o(slow_ready_d),.slow_result_valid_o(slow_valid_d),.slow_data_o(slow_data_d),.slow_flags_o(slow_flags_d));
  rv_fp_convert u_convert(.operand_i(a_q),.source_format_i(instruction_q[21:20]),
    .destination_format_i(fmt),.rounding_i(rounding_q),.result_o(converted),.flags_o(conversion_flags));
  rv_fp_round_to_int #(.EXP(8),.SIG(24)) u_round_s(.operand_i(a_s[31:0]),.rounding_i(rounding_q),
    .signal_inexact_i(instruction_q[20]),.result_o(round_s),.flags_o(round_flags_s));
  rv_fp_round_to_int u_round_d(.operand_i(a_d),.rounding_i(rounding_q),
    .signal_inexact_i(instruction_q[20]),.result_o(round_d),.flags_o(round_flags_d));
  rv_fp_immediate #(.EXP(8),.SIG(24)) u_fli_s(.index_i(instruction_q[19:15]),.value_o(fli_s));
  rv_fp_immediate u_fli_d(.index_i(instruction_q[19:15]),.value_o(fli_d));
  rv_fp_cvtmod u_modular(.operand_i(a_d),.result_o(modular));
  always_comb begin
    selected_data=fmt==0?data_s:data_d;
    selected_flags=fmt==0?flags_s:flags_d;
    selected_supported=fmt==0?fast_s:fast_d;
    if(instruction_q[6:0]==7'h53) begin
      if(instruction_q[31:27]==8) begin
        selected_supported=1;
        if(instruction_q[24:20]<=2) begin selected_data=converted;selected_flags=conversion_flags;end
        else begin
          selected_data=fmt==0?64'(round_s):round_d;
          selected_flags=fmt==0?round_flags_s:round_flags_d;
        end
      end else if(instruction_q[31:27]==30 && instruction_q[24:20]==1) begin
        selected_supported=1;selected_flags=0;selected_data=fmt==0?64'(fli_s):fli_d;
      end else if(instruction_q[31:27]==24 && instruction_q[24:20]==8) selected_data=modular;
      else if(fmt==2 && instruction_q[31:27]==28) begin
        selected_supported=1;selected_flags=0;selected_data={{48{a_q[15]}},a_q[15:0]};
      end else if(fmt==2 && instruction_q[31:27]==30) begin
        selected_supported=1;selected_flags=0;selected_data=box(a_q,2);
      end
    end
    if(destination_class_q==REG_FP) selected_data=box(selected_data,fmt);
  end
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      state_q<=IDLE;instruction_q<=0;a_q<=0;b_q<=0;c_q<=0;rounding_q<=0;
      sequence_q<=0;destination_valid_q<=0;destination_class_q<=REG_NONE;destination_phys_q<=0;
      data_q<=0;flags_q<=0;exception_q<=0;
    end else if(kill) state_q<=IDLE;
    else case(state_q)
      IDLE:if(request_valid_i && request_ready_o) begin
        instruction_q<=instruction_i;a_q<=64'(operand_a_i);b_q<=64'(operand_b_i);c_q<=64'(operand_c_i);
        rounding_q<=rounding_mode_i==7?frm_i:rounding_mode_i;
        sequence_q<=sequence_i;destination_valid_q<=destination_valid_i;
        destination_class_q<=destination_class_i;destination_phys_q<=destination_phys_i;
        exception_q<=0;flags_q<=0;state_q<=EXECUTE;
      end
      EXECUTE:begin
        if(!decoded.valid || (decoded.rounding_used && rounding_q>4)) begin
          data_q<=0;flags_q<=0;exception_q<=1;state_q<=RESULT;
        end else if(slow_operation) begin
          if(selected_slow_ready) state_q<=SLOW;
        end else begin
          data_q<=selected_data;flags_q<=selected_supported?selected_flags:5'b0;
          exception_q<=!selected_supported;state_q<=RESULT;
        end
      end
      SLOW:if(selected_slow_valid) begin
        data_q<=fmt==0?{32'hffffffff,slow_data_s}:slow_data_d;
        flags_q<=fmt==0?slow_flags_s:slow_flags_d;state_q<=RESULT;
      end
      RESULT:if(result_ready_i) state_q<=IDLE;
      default:state_q<=IDLE;
    endcase
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni || flush_valid_i)
    result_valid_o && !result_ready_i |=> result_valid_o &&
      $stable({result_sequence_o,result_destination_valid_o,result_destination_class_o,
               result_destination_phys_o,result_data_o,result_fflags_o,result_exception_valid_o}));
`endif
  initial if(XLEN!=64)$fatal(1,"RVA23 FP unit requires XLEN64/FLEN64");
endmodule

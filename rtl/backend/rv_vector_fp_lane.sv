// Vector FP element mapping. Register groups/masks/restart are owned by the
// vector controller. Vector operands are raw bits; VF scalar B is NaN-boxed.
module rv_vector_fp_lane #(
  parameter bit HAS_ZVFHMIN=1
)(
  input logic clk_i,rst_ni,request_valid_i,
  output logic request_ready_o,
  input logic [31:0] instruction_i,
  input logic [1:0] sew_size_i,
  input logic [2:0] frm_i,
  input logic mask_i,
  input logic [63:0] operand_a_i,operand_b_i,operand_c_i,
  output logic response_valid_o,
  input logic response_ready_i,
  output logic [63:0] response_data_o,
  output logic [4:0] response_flags_o,
  output logic response_exception_o
);
  import rv_ooo_pkg::*;
  import rv_vector_decode_pkg::*;
  typedef enum logic[2:0] {IDLE,PREPARE,REQUEST,WAIT_FPU,RESULT} state_t;
  state_t state_q;
  logic [31:0] instruction_q,mapped_instruction;
  logic [1:0] sew_q,format_id,source_size,destination_size,float_size,integer_size,convert_source,convert_destination;
  logic [2:0] frm_q,conversion_rounding,kind;
  logic mask_q,exception_q;
  logic [63:0] a_q,b_q,c_q,data_q,scalar_b,fp_a,fp_b,fp_c,mapped_a,mapped_b,mapped_c;
  logic [63:0] widened_a,widened_b,converted,integer_converted,direct_data,estimate_s,estimate_d;
  logic [4:0] flags_q,widen_a_flags,widen_b_flags,conversion_flags,integer_flags,direct_flags,pre_flags,estimate_flags_s,estimate_flags_d;
  logic [5:0] family;
  logic [4:0] selector;
  logic valid_operation,direct_operation,integer_destination,invert_compare,widen,widen_a,widen_b,wide_source,reduction,conversion;
  logic conversion_widen,conversion_narrow,to_integer,from_integer,float_conversion;
  vector_decode_t decoded;
  logic fpu_request_ready,fpu_valid,fpu_exception;
  logic [63:0] fpu_data;
  logic [4:0] fpu_flags;
  function automatic logic[1:0] fp_format(input logic[1:0] size);
    return size==3?2'd1:(size==1?2'd2:2'd0);
  endfunction
  function automatic logic[63:0] box(input logic[63:0] value,input logic[1:0] fmt);
    case(fmt)
      0:return {32'hffffffff,value[31:0]};
      2:return {48'hffffffffffff,value[15:0]};
      default:return value;
    endcase
  endfunction
  function automatic logic[31:0] scalar_instruction(input int op_family,input logic[1:0] fmt,
                                                   input logic[2:0] rm,input int rs2=0);
    return (32'(op_family)<<27)|(32'(fmt)<<25)|(32'(rs2)<<20)|(32'(rm)<<12)|32'h000001d3;
  endfunction
  assign decoded=decode_vector(instruction_q);
  assign family=instruction_q[31:26];assign selector=instruction_q[19:15];
  assign request_ready_o=state_q==IDLE;
  assign response_valid_o=state_q==RESULT;
  assign response_data_o=data_q;assign response_flags_o=flags_q;assign response_exception_o=exception_q;
  always_comb begin
    conversion=family==6'h12 && instruction_q[14:12]==1;
    conversion_widen=conversion && selector[3] && !selector[4];
    conversion_narrow=conversion && selector[4];kind=selector[2:0];
    source_size=sew_q+2'(conversion_narrow);destination_size=sew_q+2'(conversion_widen);
    to_integer=conversion && kind inside {3'd0,3'd1,3'd6,3'd7};
    from_integer=conversion && kind inside {3'd2,3'd3};
    float_conversion=conversion && kind inside {3'd4,3'd5};
    float_size=to_integer?source_size:destination_size;
    integer_size=to_integer?destination_size:source_size;
    convert_source=fp_format(source_size);convert_destination=fp_format(destination_size);
    conversion_rounding=(kind==6 || kind==7)?3'd1:((kind==5 && conversion_narrow)?3'd6:frm_q);
    scalar_b=b_q;
    if(instruction_q[14:12]==5 && sew_q==2 && !(&b_q[63:32]))scalar_b=64'hffffffff7fc00000;
    widen=family>=6'h30;
    wide_source=family inside {6'h34,6'h36};
    reduction=instruction_q[14:12]==1 && family inside {6'h01,6'h03,6'h05,6'h07,6'h31,6'h33};
    widen_a=widen && !wide_source;
    widen_b=widen && !reduction;
    format_id=widen?2'd1:fp_format(sew_q);
  end
  always_comb begin
    fp_a=widen_a?widened_a:box(a_q,format_id);
    fp_b=widen_b?widened_b:box(scalar_b,format_id);
    fp_c=box(c_q,format_id);
    pre_flags=(widen_a?widen_a_flags:5'b0)|(widen_b?widen_b_flags:5'b0);
    mapped_a=fp_a;mapped_b=fp_b;mapped_c=fp_c;
    mapped_instruction=scalar_instruction(0,format_id,frm_q);
    valid_operation=decoded.valid && decoded.fp_operation && frm_q<=4 && sew_q>=2;
    if(widen && sew_q!=2)valid_operation=0;
    direct_operation=0;integer_destination=0;invert_compare=0;direct_data=0;direct_flags=0;
    case(family)
      0,1,3: mapped_instruction=scalar_instruction(0,format_id,frm_q);
      2: mapped_instruction=scalar_instruction(1,format_id,frm_q);
      4,5:mapped_instruction=scalar_instruction(5,format_id,0);
      6,7:mapped_instruction=scalar_instruction(5,format_id,1);
      8:mapped_instruction=scalar_instruction(4,format_id,0);
      9:mapped_instruction=scalar_instruction(4,format_id,1);
      10:mapped_instruction=scalar_instruction(4,format_id,2);
      14,15:begin direct_operation=1;direct_data=scalar_b;end // slide insertion
      16:begin
        direct_operation=1;
        direct_data=decoded.operation==V_VFMV_F_S?box(a_q,fp_format(sew_q)):scalar_b;
      end
      23:begin
        direct_operation=1;direct_data=instruction_q[25] || mask_q?scalar_b:a_q;
      end
      18:begin
        direct_operation=1;pre_flags=0;
        valid_operation=decoded.valid && decoded.fp_operation && frm_q<=4 && sew_q>=1;
        if((conversion_widen || conversion_narrow) && sew_q==3)valid_operation=0;
        if(float_conversion)begin
          direct_data=converted;direct_flags=conversion_flags;
          if(source_size==0 || destination_size==0)valid_operation=0;
          if(source_size==1 || destination_size==1)
            valid_operation&=HAS_ZVFHMIN && (decoded.operation==V_VFWCVT_F_F_V || decoded.operation==V_VFNCVT_F_F_W);
        end else begin
          direct_data=integer_converted;direct_flags=integer_flags;
          if(float_size<2)valid_operation=0;
        end
      end
      19:begin
        case(selector)
          0:mapped_instruction=scalar_instruction(11,format_id,frm_q);
          4,5:begin
            direct_operation=1;direct_data=sew_q==3?estimate_d:estimate_s;
            direct_flags=sew_q==3?estimate_flags_d:estimate_flags_s;
          end
          16:begin mapped_instruction=scalar_instruction(28,format_id,1);integer_destination=1;end
          default:valid_operation=0;
        endcase
      end
      24:begin mapped_instruction=scalar_instruction(20,format_id,2);integer_destination=1;end
      25:begin mapped_instruction=scalar_instruction(20,format_id,0);integer_destination=1;end
      27:begin mapped_instruction=scalar_instruction(20,format_id,1);integer_destination=1;end
      28:begin mapped_instruction=scalar_instruction(20,format_id,2);integer_destination=1;invert_compare=1;end
      29,31:begin
        mapped_instruction=scalar_instruction(20,format_id,family==29?3'd1:3'd0);integer_destination=1;
        mapped_a=fp_b;mapped_b=fp_a;
      end
      32,33:begin
        mapped_instruction=scalar_instruction(3,format_id,frm_q);
        if(family==33)begin mapped_a=fp_b;mapped_b=fp_a;end
      end
      36:mapped_instruction=scalar_instruction(2,format_id,frm_q);
      39:begin mapped_instruction=scalar_instruction(1,format_id,frm_q);mapped_a=fp_b;mapped_b=fp_a;end
      40,41,42,43,44,45,46,47,60,61,62,63:begin
        // MACC forms overwrite the addend; MADD forms overwrite a multiplicand.
        mapped_a=fp_b;mapped_b=family[2]?fp_a:fp_c;mapped_c=family[2]?fp_c:fp_a;
        case(family[1:0])
          0:mapped_instruction=32'h43;
          1:mapped_instruction=32'h4f;
          2:mapped_instruction=32'h47;
          3:mapped_instruction=32'h4b;
        endcase
        mapped_instruction|=(32'(format_id)<<25)|(32'(frm_q)<<12)|32'h180;
      end
      48,49,51,52:mapped_instruction=scalar_instruction(0,format_id,frm_q);
      50,54:mapped_instruction=scalar_instruction(1,format_id,frm_q);
      56:mapped_instruction=scalar_instruction(2,format_id,frm_q);
      default:valid_operation=0;
    endcase
    if(direct_operation && decoded.operation!=V_VFMV_F_S)
      direct_data&=64'((128'b1<<(8<<destination_size))-1);
  end
  rv_fp_convert u_widen_a(.operand_i(box(a_q,0)),.source_format_i(2'd0),.destination_format_i(2'd1),
    .rounding_i(3'd0),.result_o(widened_a),.flags_o(widen_a_flags));
  rv_fp_convert u_widen_b(.operand_i(box(scalar_b,0)),.source_format_i(2'd0),.destination_format_i(2'd1),
    .rounding_i(3'd0),.result_o(widened_b),.flags_o(widen_b_flags));
  rv_fp_convert u_float_convert(.operand_i(box(a_q,convert_source)),.source_format_i(convert_source),
    .destination_format_i(convert_destination),.rounding_i(conversion_rounding),.result_o(converted),.flags_o(conversion_flags));
  rv_vector_fp_integer u_integer_convert(.operand_i(a_q),.fp_double_i(float_size==3),.integer_size_i(integer_size),
    .unsigned_i(!kind[0]),.to_float_i(from_integer),.rounding_i(conversion_rounding),.result_o(integer_converted),.flags_o(integer_flags));
  wire [31:0] estimate_single;
  assign estimate_s=64'(estimate_single);
  rv_vector_fp_estimate u_estimate_s(.operand_i(a_q[31:0]),.reciprocal_sqrt_i(selector==4),
    .rounding_i(frm_q),.result_o(estimate_single),.flags_o(estimate_flags_s));
  rv_vector_fp_estimate #(.EXP(11),.FRAC(52)) u_estimate_d(.operand_i(a_q),.reciprocal_sqrt_i(selector==4),
    .rounding_i(frm_q),.result_o(estimate_d),.flags_o(estimate_flags_d));
  rv_fpu_rva23 u_fpu(.clk_i,.rst_ni,.request_valid_i(state_q==REQUEST),.request_ready_o(fpu_request_ready),
    .instruction_i(mapped_instruction),.operand_a_i(mapped_a),.operand_b_i(mapped_b),.operand_c_i(mapped_c),
    .rounding_mode_i(mapped_instruction[14:12]),.frm_i(3'b0),.sequence_i('0),
    .destination_valid_i(1'b1),.destination_class_i(integer_destination?REG_INT:REG_FP),.destination_phys_i('0),
    .flush_valid_i(1'b0),.flush_all_i(1'b0),.flush_sequence_i('0),.result_valid_o(fpu_valid),
    .result_ready_i(state_q==WAIT_FPU),.result_sequence_o(),.result_destination_valid_o(),
    .result_destination_class_o(),.result_destination_phys_o(),.result_data_o(fpu_data),.result_fflags_o(fpu_flags),
    .result_exception_valid_o(fpu_exception),.result_exception_cause_o(),.result_exception_tval_o());
  always_ff @(posedge clk_i)begin
    if(!rst_ni)begin
      state_q<=IDLE;instruction_q<=0;sew_q<=0;frm_q<=0;mask_q<=0;
      a_q<=0;b_q<=0;c_q<=0;data_q<=0;flags_q<=0;exception_q<=0;
    end else case(state_q)
      IDLE:if(request_valid_i)begin
        instruction_q<=instruction_i;sew_q<=sew_size_i;frm_q<=frm_i;mask_q<=mask_i;
        a_q<=operand_a_i;b_q<=operand_b_i;c_q<=operand_c_i;data_q<=0;flags_q<=0;exception_q<=0;state_q<=PREPARE;
      end
      PREPARE:begin
        if(!valid_operation)begin exception_q<=1;state_q<=RESULT;end
        else if(direct_operation)begin data_q<=direct_data;flags_q<=direct_flags;state_q<=RESULT;end
        else state_q<=REQUEST;
      end
      REQUEST:if(fpu_request_ready)state_q<=WAIT_FPU;
      WAIT_FPU:if(fpu_valid)begin
        data_q<=integer_destination?(invert_compare?64'(!fpu_data[0]):fpu_data):
          (fpu_data&64'((128'b1<<(widen?64:(8<<sew_q)))-1));
        flags_q<=fpu_flags|pre_flags;exception_q<=fpu_exception;state_q<=RESULT;
      end
      RESULT:if(response_ready_i)state_q<=IDLE;
      default:state_q<=IDLE;
    endcase
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    response_valid_o && !response_ready_i |=> response_valid_o && $stable({response_data_o,response_flags_o,response_exception_o}));
`endif
endmodule

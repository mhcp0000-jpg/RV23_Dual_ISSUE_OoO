// Serialized architectural vector owner. The caller drains older traffic and
// cannot cancel accepted operations: completed memory elements survive faults.
// Standalone execution does not establish architectural core integration.
module rv_vector_engine #(
  parameter int unsigned ADDRESS_WIDTH=64,
  parameter bit HAS_MMU=0,HAS_SSNPM=0
)(
  input logic clk_i,rst_ni,request_valid_i,
  output logic request_ready_o,
  input logic [31:0] instruction_i,
  input logic [63:0] scalar_a_i,scalar_b_i,
  input logic fp_state_enabled_i=1,
  input logic [2:0] frm_i=0,
  output logic response_valid_o,
  input logic response_ready_i,
  output logic [63:0] response_data_o,
  output logic response_exception_o,
  output logic [5:0] response_cause_o,
  output logic [63:0] response_tval_o,
  output logic [4:0] response_flags_o,
  output logic [63:0] response_guest_address_o,
  output logic response_implicit_guest_access_o,
  input logic invalidate_i=0,
  input rv_ooo_pkg::privilege_e privilege_i=rv_ooo_pkg::PRIV_M,
  input logic [63:0] mstatus_i=0,satp_i=0,menvcfg_i=0,senvcfg_i=0,
  input logic virtual_i=0,hs_mxr_i=0,guest_pbmt_enable_i=0,
  input logic [63:0] vsatp_i=0,hgatp_i=0,
  input logic [1:0] pmm_i=0,
  input logic [7:0][7:0] pmpcfg_i=0,
  input logic [7:0][ADDRESS_WIDTH-3:0] pmpaddr_i=0,
  output logic ptw_valid_o,ptw_device_o,
  input logic ptw_ready_i=0,
  output logic [55:0] ptw_address_o,
  input logic ptw_response_valid_i=0,
  output logic ptw_response_ready_o,
  input logic [63:0] ptw_data_i=0,
  input logic ptw_error_i=0,
  output logic memory_valid_o,
  input logic memory_ready_i=0,
  output logic memory_write_o,
  output logic memory_device_o,
  output logic [2:0] memory_size_o,
  output logic [31:0] memory_address_o,
  output logic [63:0] memory_data_o,
  output logic [7:0] memory_strobe_o,
  input logic memory_response_valid_i=0,
  output logic memory_response_ready_o,
  input logic [63:0] memory_response_data_i=0,
  input logic memory_response_error_i=0,
  input logic csr_write_i,
  input logic [11:0] csr_address_i,
  input logic [63:0] csr_data_i,
  output logic [63:0] vl_o,vtype_o,vstart_o,
  output logic [1:0] vxrm_o,
  output logic vxsat_o,state_dirty_o
);
  import rv_vector_decode_pkg::*;
  typedef enum logic[3:0] {IDLE,CHECK,ELEMENT,GATHER,FINISH,RESULT,FP_REQUEST,FP_WAIT,MEM_ISSUE,MEM_WAIT,
    INT_DRAIN,INT_REDUCE_WAIT,DIV_REQUEST,DIV_WAIT,WB_DRAIN} state_t;
  state_t state_q;
  logic [31:0] instruction_q;
  logic [63:0] scalar_a_q,scalar_b_q,vl_q,vtype_q,result_q,accumulator_q,gather_q;
  logic [6:0] vstart_q;
  logic [7:0] index_q,packed_index_q;
  logic [1:0] vxrm_q;
  logic vxsat_q,exception_q,seen_q;
  logic fp_enabled_q,fp_probe_q,fp_ready,fp_valid,fp_exception;
  logic [2:0] frm_q;
  logic [63:0] fp_data,fp_operand_b;
  logic [4:0] fp_flags,flags_q;
  logic [5:0] cause_q,mem_cause;
  logic [63:0] tval_q,mem_tval,mem_address,mem_result;
  logic [63:0] guest_q,mem_guest_address;
  logic implicit_q,mem_implicit;
  logic mem_ready,mem_valid,mem_fault,mem_indexed,mem_whole,mem_mask,mem_ff;
  logic [2:0] field_q;
  logic [1:0] mem_size,index_size;
  int signed mem_exponent,index_exponent;
  int unsigned mem_fields,mem_registers,index_registers,mem_base;
  logic fp_conversion,fp_reduction,fp_widening,fp_narrowing,fp_wide_source,fp_mask_result,fp_slide,fp_insert;
  vector_decode_t decoded;
  vector_integer_operation_e operation;
  logic config_valid;
  logic [63:0] config_vl,config_type,config_maximum;
  logic [2:0][4:0] read_base;
  logic [2:0][7:0] read_element;
  logic [2:0][1:0] read_size;
  logic [2:0] read_mask,read_valid;
  logic [2:0][63:0] read_data;
  logic [2:0][127:0] read_packed;
  logic [15:0] packed_mask;
  logic mask_bit,rf_write,rf_mask;
  logic [4:0] rf_base;
  logic [7:0] rf_element;
  logic [1:0] rf_size;
  logic [63:0] rf_data,a,b,c,control_b;
  logic [3:0][63:0] alu_result;
  logic [3:0] alu_supported,alu_sat;
  typedef struct packed {
    logic [4:0] base;
    logic [7:0] element;
    logic [1:0] size,sew;
    logic mask,reduction,packed_mode;
    logic [15:0] active_mask;
  } integer_metadata_t;
  integer_metadata_t int_meta_q,int_result_meta_q;
  vector_integer_operation_e int_operation_q;
  logic integer_pipeline,integer_divide,int_valid_q,int_result_valid_q,int_saturated_q;
  logic [63:0] int_a_q,int_b_q,int_c_q,int_result_q;
  logic packed_integer;
  int unsigned packed_capacity,packed_count;
  logic [15:0] packed_active;
  logic [127:0] packed_b,int_packed_a_q,int_packed_b_q,int_packed_c_q,simd_result;
  logic [15:0] int_packed_carry_q,simd_saturated;
  logic [127:0] packed_result,packed_write_mask,int_wide_result_q,int_write_mask_q;
  logic int_carry_q,int_wide_q;
  logic [1:0] int_rounding_q,int_extension_q;
  logic div_ready,div_valid;
  logic [63:0] div_result;
  logic rf_write_q,rf_mask_q;
  logic [4:0] rf_base_q;
  logic [7:0] rf_element_q;
  logic [1:0] rf_size_q;
  logic [63:0] rf_data_q;
  logic rf_packed,rf_packed_q;
  logic [127:0] rf_packed_data,rf_packed_data_q,rf_bit_mask,rf_bit_mask_q;
  logic [1:0] sew_size,destination_size,source2_size,extension_factor;
  logic reduction,widening,narrowing,wide_source,mask_result,mask_logic,whole_move,scalar_move;
  logic element_active,carry_operation,special_operation,group_valid,source_out_of_bounds;
  int signed lmul_exponent,destination_exponent,source2_exponent;
  int unsigned sew,maximum,whole_registers,effective_length;
  function automatic logic legal_group(input int base,input int exponent);
    int registers;
    registers=exponent>0?(1<<exponent):1;
    return exponent>=-3 && exponent<=3 && (base&(registers-1))==0 && base+registers<=32;
  endfunction
  function automatic logic [63:0] sext(input logic[63:0] value,input int bits);
    return value[bits-1]?(value|(~64'b0<<bits)):(value&~(~64'b0<<bits));
  endfunction
  function automatic logic overlaps(input int base_a,count_a,base_b,count_b);
    return base_a<base_b+count_b && base_b<base_a+count_a;
  endfunction
  function automatic logic source_groups_disjoint(input int base_a,exp_a,base_b,exp_b);
    return !overlaps(base_a,1<<((exp_a>0)?exp_a:0),base_b,1<<((exp_b>0)?exp_b:0));
  endfunction
  function automatic logic legal_overlap(input int dst,dexp,dsize,src,sexp,ssize);
    int dr,sr;
    dr=dexp>0?(1<<dexp):1;sr=sexp>0?(1<<sexp):1;
    return !overlaps(dst,dr,src,sr) || dsize==ssize ||
      (dsize<ssize && dst==src) ||
      (dsize>ssize && sexp>=0 && dst+dr==src+sr);
  endfunction
  assign request_ready_o=state_q==IDLE && !csr_write_i;
  assign response_valid_o=state_q==RESULT;
  assign response_data_o=result_q;assign response_exception_o=exception_q;
  assign response_flags_o=flags_q;
  assign response_cause_o=cause_q;assign response_tval_o=tval_q;
  assign response_guest_address_o=guest_q;assign response_implicit_guest_access_o=implicit_q;
  assign vl_o=vl_q;assign vtype_o=vtype_q;assign vstart_o=64'(vstart_q);
  assign vxrm_o=vxrm_q;assign vxsat_o=vxsat_q;
  assign decoded=decode_vector(instruction_q);
  assign operation=integer_operation(decoded.operation);
  rv_vector_config u_config(.instruction_i(instruction_q),.avl_register_i(scalar_a_q),
    .type_register_i(scalar_b_q),.old_vl_i(vl_q),.old_type_i(vtype_q),
    .valid_o(config_valid),.vl_o(config_vl),.type_o(config_type),.maximum_o(config_maximum));
  rv_vector_register_file u_registers(.clk_i,.rst_ni,.capture_i(request_valid_i && request_ready_o),
    .read_base_i(read_base),.read_element_i(read_element),.read_size_i(read_size),.read_mask_i(read_mask),
    .read_data_o(read_data),.read_packed_data_o(read_packed),.read_valid_o(read_valid),
    .mask_element_i(index_q[6:0]),.mask_o(mask_bit),.packed_mask_o(packed_mask),
    .write_valid_i(rf_write_q),.write_base_i(rf_base_q),.write_element_i(rf_element_q),.write_size_i(rf_size_q),
    .write_mask_i(rf_mask_q),.write_data_i(rf_data_q),.write_packed_i(rf_packed_q),
    .write_packed_data_i(rf_packed_data_q),.write_bit_mask_i(rf_bit_mask_q));
  for(genvar w=0;w<4;w++) begin:g_alu
    rv_vector_integer_alu #(.WIDTH(8<<w),.EXTERNAL_DIVIDE(1)) u_alu(.operation_i(int_operation_q),
      .operand_a_i(int_a_q),.operand_b_i(int_b_q),.accumulator_i(int_c_q),
      .carry_i(int_carry_q),.wide_source_i(int_wide_q),
      .rounding_i(int_rounding_q),.extension_factor_i(int_extension_q),
      .result_o(alu_result[w]),.saturated_o(alu_sat[w]),.supported_o());
    // Only legality is live during CHECK. Unconnected arithmetic is pruned.
    rv_vector_integer_alu #(.WIDTH(8<<w),.EXTERNAL_DIVIDE(1)) u_legality(.operation_i(operation),
      .operand_a_i(64'b0),.operand_b_i(64'b0),.accumulator_i(64'b0),
      .carry_i(1'b0),.wide_source_i(wide_source),.rounding_i(vxrm_q),.extension_factor_i(extension_factor),
      .result_o(),.saturated_o(),.supported_o(alu_supported[w]));
  end
  rv_vector_simd_alu u_simd(.operation_i(int_operation_q),.sew_size_i(int_meta_q.sew),.rounding_i(int_rounding_q),
    .a_i(int_packed_a_q),.b_i(int_packed_b_q),.c_i(int_packed_c_q),.carry_i(int_packed_carry_q),
    .result_o(simd_result),.saturated_o(simd_saturated));
  rv_vector_divider u_integer_divider(.clk_i,.rst_ni,.request_valid_i(state_q==DIV_REQUEST),.request_ready_o(div_ready),
    .sew_size_i(int_meta_q.sew),.signed_i(int_operation_q inside {VI_VDIV,VI_VREM}),
    .remainder_i(int_operation_q inside {VI_VREM,VI_VREMU}),.operand_a_i(int_a_q),.operand_b_i(int_b_q),
    .response_valid_o(div_valid),.response_ready_i(state_q==DIV_WAIT),.result_o(div_result));
  assign fp_operand_b=reduction?accumulator_q:(decoded.scalar_source_used[0]?scalar_a_q:read_data[1]);
  rv_vector_fp_lane u_fp(.clk_i,.rst_ni,.request_valid_i(state_q==FP_REQUEST),.request_ready_o(fp_ready),
    .instruction_i(instruction_q),.sew_size_i(sew_size),.frm_i(frm_q),.mask_i(mask_bit),
    .operand_a_i(fp_probe_q?64'b0:read_data[0]),.operand_b_i(fp_probe_q?64'b0:fp_operand_b),
    .operand_c_i(fp_probe_q?64'b0:read_data[2]),.response_valid_o(fp_valid),.response_ready_i(state_q==FP_WAIT),
    .response_data_o(fp_data),.response_flags_o(fp_flags),.response_exception_o(fp_exception));
  rv23_hypervisor_memory_head #(.ADDRESS_WIDTH(ADDRESS_WIDTH),.HAS_MMU(HAS_MMU),.HAS_SSNPM(HAS_SSNPM)) u_memory(
    .clk_i,.rst_ni,.invalidate_i,.request_valid_i(state_q==MEM_ISSUE),.request_ready_o(mem_ready),
    .address_i(mem_address),.operand_i(read_data[2]),.size_i({1'b0,mem_size}),
    .write_i(decoded.store),.unsigned_i(1'b1),.floating_i(1'b0),.privilege_i,
    // vstart resumes at the segment boundary and can repeat earlier fields.
    .require_idempotent_i(mem_fields>1),
    .mstatus_i,.satp_i,.menvcfg_i,.senvcfg_i,.pmpcfg_i,.pmpaddr_i,
    .virtual_i,.hs_mxr_i,.guest_pbmt_enable_i,.vsatp_i,.hgatp_i,.pmm_i,
    .response_valid_o(mem_valid),.response_ready_i(state_q==MEM_WAIT),
    .response_data_o(mem_result),.response_tval_o(mem_tval),.response_exception_o(mem_fault),.response_cause_o(mem_cause),
    .response_guest_address_o(mem_guest_address),.response_implicit_guest_access_o(mem_implicit),
    .ptw_valid_o,.ptw_device_o,.ptw_ready_i,.ptw_address_o,.ptw_response_valid_i,.ptw_response_ready_o,
    .ptw_data_i,.ptw_error_i,.memory_valid_o,.memory_ready_i,.memory_write_o,.memory_device_o,.memory_size_o,.memory_address_o,
    .memory_data_o,.memory_strobe_o,.memory_response_valid_i,.memory_response_ready_o,
    .memory_response_data_i,.memory_response_error_i);
  always_comb begin
    sew_size=vtype_q[4:3];sew=8<<sew_size;
    lmul_exponent=int'($signed(vtype_q[2:0]));
    maximum=(lmul_exponent<0?(128>>(-lmul_exponent)):(128<<lmul_exponent))/sew;
    fp_conversion=decoded.fp_operation && instruction_q[31:26]==6'h12;
    fp_reduction=decoded.fp_operation && instruction_q[14:12]==1 &&
      instruction_q[31:26] inside {6'h01,6'h03,6'h05,6'h07,6'h31,6'h33};
    fp_widening=decoded.fp_operation && (instruction_q[31:26]>=6'h30 ||
      (fp_conversion && instruction_q[18] && !instruction_q[19]));
    fp_narrowing=fp_conversion && instruction_q[19];
    fp_wide_source=decoded.fp_operation && instruction_q[31:26] inside {6'h34,6'h36};
    fp_mask_result=decoded.fp_operation && instruction_q[31:26] inside {6'h18,6'h19,6'h1b,6'h1c,6'h1d,6'h1f};
    fp_slide=decoded.fp_operation && instruction_q[31:26] inside {6'h0e,6'h0f};
    fp_insert=(instruction_q[31:26]==6'h0e && index_q==0) || (instruction_q[31:26]==6'h0f && index_q==vl_q-1);
    reduction=fp_reduction || operation inside {VI_VREDSUM,VI_VREDAND,VI_VREDOR,VI_VREDXOR,VI_VREDMINU,
      VI_VREDMIN,VI_VREDMAXU,VI_VREDMAX,VI_VWREDSUM,VI_VWREDSUMU};
    widening=fp_widening || operation inside {VI_VWADDU,VI_VWADD,VI_VWSUBU,VI_VWSUB,VI_VWMULU,VI_VWMULSU,
      VI_VWMUL,VI_VWMACCU,VI_VWMACC,VI_VWMACCSU,VI_VWMACCUS,VI_VWREDSUM,VI_VWREDSUMU,VI_VWSLL};
    narrowing=fp_narrowing || operation inside {VI_VNSRL,VI_VNSRA,VI_VNCLIPU,VI_VNCLIP};
    wide_source=fp_wide_source || (operation inside {VI_VWADDU,VI_VWADD,VI_VWSUBU,VI_VWSUB} && instruction_q[28]);
    mask_result=fp_mask_result || operation inside {VI_VMADC,VI_VMSBC,VI_VMSEQ,VI_VMSNE,VI_VMSLTU,VI_VMSLT,
      VI_VMSLEU,VI_VMSLE,VI_VMSGTU,VI_VMSGT,VI_VMSBF,VI_VMSOF,VI_VMSIF};
    mask_logic=operation inside {VI_VMAND,VI_VMANDN,VI_VMOR,VI_VMXOR,VI_VMORN,VI_VMNAND,VI_VMNOR,VI_VMXNOR};
    mask_result|=mask_logic;
    whole_move=operation inside {VI_VMV1R,VI_VMV2R,VI_VMV4R,VI_VMV8R};
    scalar_move=decoded.operation inside {V_VMV_X_S,V_VMV_S_X,V_VFMV_F_S,V_VFMV_S_F};
    whole_registers=int'(instruction_q[19:15])+1;
    effective_length=whole_move?(whole_registers*128/sew):int'(vl_q);
    extension_factor=2'((8-(int'(instruction_q[19:15])&~1))/2);
    destination_size=sew_size+2'(widening);
    source2_size=sew_size+2'(wide_source || narrowing);
    if(operation inside {VI_VZEXT,VI_VSEXT})source2_size=sew_size-extension_factor;
    destination_exponent=lmul_exponent+int'(widening);
    source2_exponent=lmul_exponent+int'(wide_source || narrowing);
    if(operation inside {VI_VZEXT,VI_VSEXT})source2_exponent=lmul_exponent-int'(extension_factor);
    if(mask_result || reduction || scalar_move)destination_exponent=0;
    if(mask_logic || scalar_move || decoded.operation==V_VCPOP_M ||
       operation inside {VI_VMSBF,VI_VMSOF,VI_VMSIF,VI_VIOTA,VI_VFIRST})source2_exponent=0;
    group_valid=legal_group(int'(instruction_q[24:20]),source2_exponent) &&
      (decoded.scalar_destination || legal_group(int'(instruction_q[11:7]),destination_exponent));
    if(instruction_q[14:12] inside {3'd0,3'd2} && !reduction && !scalar_move &&
       !(operation inside {VI_VZEXT,VI_VSEXT,VI_VBREV,VI_VBREV8,VI_VREV8,VI_VCLZ,VI_VCTZ,VI_VCPOP,
                           VI_VMSBF,VI_VMSOF,VI_VMSIF,VI_VIOTA,VI_VID,VI_VFIRST}))
      group_valid&=legal_group(int'(instruction_q[19:15]),(mask_logic || operation==VI_VCOMPRESS)?0:
        (operation==VI_VRGATHEREI16?lmul_exponent+1-int'(sew_size):lmul_exponent));
    if(decoded.fp_operation && instruction_q[14:12]==1 && !reduction &&
       !(instruction_q[31:26] inside {6'h10,6'h12,6'h13}))
      group_valid&=legal_group(int'(instruction_q[19:15]),lmul_exponent);
    if(widening || narrowing)group_valid&=sew_size<3;
    if(operation inside {VI_VZEXT,VI_VSEXT})group_valid&=sew_size>=extension_factor;
    // A physical register may not supply two explicit sources at different EEWs.
    if((instruction_q[14:12]==0 && narrowing) ||
       (instruction_q[14:12]==2 && wide_source) ||
       (instruction_q[14:12]==1 && fp_wide_source))
      group_valid&=source_groups_disjoint(int'(instruction_q[24:20]),source2_exponent,
        int'(instruction_q[19:15]),lmul_exponent);
    if(operation==VI_VRGATHEREI16 && sew_size!=1)
      group_valid&=source_groups_disjoint(int'(instruction_q[24:20]),source2_exponent,
        int'(instruction_q[19:15]),lmul_exponent+1-int'(sew_size));
    if((reduction && widening) || operation==VI_VCOMPRESS)
      group_valid&=source_groups_disjoint(int'(instruction_q[24:20]),source2_exponent,
        int'(instruction_q[19:15]),0);
    // RVV 1.0 section 5.2 overlap rules are architectural legality, even
    // though source snapshots also avoid intra-operation RAW hazards.
    if(!reduction && !scalar_move && !decoded.scalar_destination && !decoded.memory && !whole_move)begin
      group_valid&=legal_overlap(int'(instruction_q[11:7]),destination_exponent,mask_result?-3:int'(destination_size),
        int'(instruction_q[24:20]),source2_exponent,
        (mask_logic || operation inside {VI_VMSBF,VI_VMSOF,VI_VMSIF,VI_VIOTA,VI_VFIRST} || decoded.operation==V_VCPOP_M)?-3:int'(source2_size));
      if(!decoded.scalar_source_used[0] && instruction_q[14:12] inside {3'd0,3'd1,3'd2} &&
         !(operation inside {VI_VZEXT,VI_VSEXT,VI_VBREV,VI_VBREV8,VI_VREV8,VI_VCLZ,VI_VCTZ,VI_VCPOP,
                            VI_VMSBF,VI_VMSOF,VI_VMSIF,VI_VIOTA,VI_VID,VI_VFIRST}) &&
         !(decoded.fp_operation && instruction_q[31:26] inside {6'h10,6'h12,6'h13}))
        group_valid&=legal_overlap(int'(instruction_q[11:7]),destination_exponent,mask_result?-3:int'(destination_size),
          int'(instruction_q[19:15]),(mask_logic || operation==VI_VCOMPRESS)?0:
          (operation==VI_VRGATHEREI16?lmul_exponent+1-int'(sew_size):lmul_exponent),
          (mask_logic || operation==VI_VCOMPRESS)?-3:(operation==VI_VRGATHEREI16?1:int'(sew_size)));
      if(operation inside {VI_VSLIDEUP,VI_VSLIDE1UP,VI_VRGATHER,VI_VRGATHEREI16,VI_VCOMPRESS} ||
         (fp_slide && instruction_q[31:26]==6'h0e) || operation inside {VI_VMSBF,VI_VMSOF,VI_VMSIF,VI_VIOTA})
        group_valid&=!overlaps(int'(instruction_q[11:7]),destination_exponent>0?(1<<destination_exponent):1,
          int'(instruction_q[24:20]),source2_exponent>0?(1<<source2_exponent):1);
      if(operation inside {VI_VRGATHER,VI_VRGATHEREI16,VI_VCOMPRESS} && !decoded.scalar_source_used[0] && instruction_q[14:12]!=3)
        group_valid&=!overlaps(int'(instruction_q[11:7]),destination_exponent>0?(1<<destination_exponent):1,
          int'(instruction_q[19:15]),operation==VI_VCOMPRESS?1:
            (operation==VI_VRGATHEREI16?(lmul_exponent+1-int'(sew_size)>0?(1<<(lmul_exponent+1-int'(sew_size))):1):
             (lmul_exponent>0?(1<<lmul_exponent):1)));
    end
    mem_indexed=instruction_q[26];
    mem_whole=decoded.memory && instruction_q[27:26]==0 && instruction_q[24:20]==8;
    mem_mask=decoded.memory && instruction_q[27:26]==0 && instruction_q[24:20]==11;
    mem_ff=decoded.memory && instruction_q[27:26]==0 && instruction_q[24:20]==16 && !decoded.store;
    index_size=instruction_q[14:12]==0?0:instruction_q[13:12];
    mem_size=mem_indexed?sew_size:index_size;
    mem_exponent=lmul_exponent+int'(mem_size)-int'(sew_size);
    index_exponent=lmul_exponent+int'(index_size)-int'(sew_size);
    mem_fields=int'(instruction_q[31:29])+1;
    if(mem_whole)begin
      mem_exponent=$clog2(mem_fields);effective_length=mem_fields*128/(8<<mem_size);mem_fields=1;
    end
    if(mem_mask)begin mem_exponent=0;effective_length=(int'(vl_q)+7)/8;end
    mem_registers=mem_exponent>0?(1<<mem_exponent):1;
    index_registers=index_exponent>0?(1<<index_exponent):1;
    mem_base=int'(instruction_q[11:7])+int'(field_q)*mem_registers;
    if(decoded.memory)begin
      group_valid=legal_group(int'(instruction_q[11:7]),mem_exponent) &&
        int'(instruction_q[11:7])+mem_fields*mem_registers<=32 &&
        (mem_exponent<0?mem_fields<=8:mem_fields*mem_registers<=8);
      if(mem_indexed)begin
        group_valid&=legal_group(int'(instruction_q[24:20]),index_exponent);
        if(decoded.store)begin
          if(mem_size!=index_size)
            group_valid&=!overlaps(int'(instruction_q[11:7]),mem_fields*mem_registers,
              int'(instruction_q[24:20]),index_registers);
        end else begin
          if(mem_fields>1)group_valid&=!overlaps(int'(instruction_q[11:7]),mem_fields*mem_registers,
            int'(instruction_q[24:20]),index_registers);
          else group_valid&=legal_overlap(int'(instruction_q[11:7]),mem_exponent,int'(mem_size),
            int'(instruction_q[24:20]),index_exponent,int'(index_size));
        end
      end
    end
    if(!instruction_q[25] && instruction_q[11:7]==0 && !mask_result && !reduction &&
       !decoded.scalar_destination && !(decoded.memory && decoded.store))group_valid=0;
    if(whole_move)group_valid=legal_group(int'(instruction_q[11:7]),$clog2(whole_registers)) &&
      legal_group(int'(instruction_q[24:20]),$clog2(whole_registers));
    carry_operation=decoded.operation==V_VFMERGE_VFM || operation inside {VI_VADC,VI_VMADC,VI_VSBC,VI_VMSBC,VI_VMERGE};
    element_active=instruction_q[25] || mask_bit || carry_operation || whole_move;
    special_operation=decoded.memory || decoded.fp_operation || whole_move || scalar_move || operation inside {VI_VRGATHER,VI_VRGATHEREI16,
      VI_VSLIDEUP,VI_VSLIDEDOWN,VI_VSLIDE1UP,VI_VSLIDE1DOWN,VI_VCOMPRESS,
      VI_VMSBF,VI_VMSOF,VI_VMSIF,VI_VIOTA,VI_VID,VI_VFIRST};
    integer_pipeline=!special_operation && !decoded.scalar_destination;
    integer_divide=operation inside {VI_VDIV,VI_VDIVU,VI_VREM,VI_VREMU};
    packed_integer=integer_pipeline && !integer_divide && !reduction && !widening && !narrowing &&
      !mask_logic && !(operation inside {VI_VZEXT,VI_VSEXT});
    read_base[0]=instruction_q[24:20];read_base[1]=instruction_q[19:15];read_base[2]=instruction_q[11:7];
    read_element[0]=index_q;read_element[1]=index_q;read_element[2]=index_q;
    read_size[0]=source2_size;read_size[1]=sew_size;read_size[2]=destination_size;
    read_mask[0]=mask_logic || operation inside {VI_VMSBF,VI_VMSOF,VI_VMSIF,VI_VIOTA,VI_VFIRST} || decoded.operation==V_VCPOP_M;
    read_mask[1]=mask_logic || operation==VI_VCOMPRESS;read_mask[2]=0;
    if(operation==VI_VRGATHEREI16)read_size[1]=1;
    if(reduction)begin read_element[1]=0;read_size[1]=destination_size;end
    if(scalar_move)read_element[0]=0;
    if(fp_slide)read_element[0]=(instruction_q[31:26]==6'h0e) ? index_q-1'b1:index_q+1'b1;
    control_b=instruction_q[14:12]==3?64'(instruction_q[19:15]):scalar_a_q;
    source_out_of_bounds=0;
    if(operation inside {VI_VSLIDEUP,VI_VSLIDEDOWN,VI_VSLIDE1UP,VI_VSLIDE1DOWN}) begin
      if(operation==VI_VSLIDEUP)begin read_element[0]=8'(64'(index_q)-control_b);source_out_of_bounds=64'(index_q)<control_b;end
      if(operation==VI_VSLIDEDOWN)begin read_element[0]=8'(64'(index_q)+control_b);source_out_of_bounds=control_b>=64'(maximum) || 64'(index_q)+control_b>=64'(maximum);end
      if(operation==VI_VSLIDE1UP)read_element[0]=index_q-1'b1;
      if(operation==VI_VSLIDE1DOWN)read_element[0]=index_q+1'b1;
    end
    if(state_q==GATHER)begin read_element[0]=gather_q[7:0];source_out_of_bounds=gather_q>=64'(maximum);end
    if(decoded.memory)begin
      read_base[0]=instruction_q[24:20];read_size[0]=index_size;read_element[0]=index_q;read_mask[0]=0;
      read_base[2]=5'(mem_base);read_size[2]=mem_size;read_element[2]=index_q;read_mask[2]=0;
    end
  end
  always_comb begin
    mem_address=scalar_a_q+64'(field_q)*(64'b1<<mem_size);
    if(mem_indexed)mem_address+=read_data[0];
    else if(instruction_q[27:26]==2)mem_address+=64'(index_q)*scalar_b_q;
    else mem_address+=64'(index_q)*64'(mem_fields)*(64'b1<<mem_size);
  end
  always_comb begin
    a=read_data[0];b=read_data[1];c=read_data[2];
    if(decoded.scalar_source_used[0])b=scalar_a_q;
    if(instruction_q[14:12]==3) begin
      if(operation inside {VI_VSLL,VI_VSRL,VI_VSRA,VI_VSSRL,VI_VSSRA,VI_VNSRL,VI_VNSRA,
          VI_VNCLIP,VI_VNCLIPU,VI_VRGATHER,VI_VSLIDEUP,VI_VSLIDEDOWN,VI_VROR,VI_VWSLL})
        b=64'(instruction_q[19:15])|(operation==VI_VROR?64'(instruction_q[26])<<5:64'b0);
      else b={{59{instruction_q[19]}},instruction_q[19:15]};
    end
    if(reduction) begin
      b=accumulator_q;c=accumulator_q;
    end
  end
  always_comb begin
    packed_capacity=16>>sew_size;
    packed_count=packed_capacity-(int'(index_q)&(packed_capacity-1));
    if(index_q>=effective_length)packed_count=0;
    else if(packed_count>effective_length-int'(index_q))packed_count=effective_length-int'(index_q);
    packed_active=0;
    for(int e=0;e<16;e++)packed_active[e]=e<packed_count && (instruction_q[25] || packed_mask[e] || carry_operation);
    packed_b=read_packed[1];
    if(decoded.scalar_source_used[0] || instruction_q[14:12]==3)case(sew_size)
      0:for(int e=0;e<16;e++)packed_b[e*8+:8]=b[7:0];
      1:for(int e=0;e<8;e++)packed_b[e*16+:16]=b[15:0];
      2:for(int e=0;e<4;e++)packed_b[e*32+:32]=b[31:0];
      default:for(int e=0;e<2;e++)packed_b[e*64+:64]=b;
    endcase
    packed_result=int_meta_q.mask?128'b0:simd_result;packed_write_mask=0;
    case(int_meta_q.sew)
      0:for(int e=0;e<16;e++)if(int_meta_q.active_mask[e])begin
        if(int_meta_q.mask)begin packed_result[e]=simd_result[e*8];packed_write_mask[e]=1;end
        else packed_write_mask[e*8+:8]='1;
      end
      1:for(int e=0;e<8;e++)if(int_meta_q.active_mask[e])begin
        if(int_meta_q.mask)begin packed_result[e]=simd_result[e*16];packed_write_mask[e]=1;end
        else packed_write_mask[e*16+:16]='1;
      end
      2:for(int e=0;e<4;e++)if(int_meta_q.active_mask[e])begin
        if(int_meta_q.mask)begin packed_result[e]=simd_result[e*32];packed_write_mask[e]=1;end
        else packed_write_mask[e*32+:32]='1;
      end
      default:for(int e=0;e<2;e++)if(int_meta_q.active_mask[e])begin
        if(int_meta_q.mask)begin packed_result[e]=simd_result[e*64];packed_write_mask[e]=1;end
        else packed_write_mask[e*64+:64]='1;
      end
    endcase
  end
  always_comb begin
    rf_write=0;rf_base=instruction_q[11:7];rf_element=index_q;rf_size=destination_size;
    rf_packed=0;rf_packed_data=0;rf_bit_mask=0;
    rf_mask=mask_result;rf_data=0;
    if(state_q==ELEMENT && special_operation && index_q<effective_length && element_active && !reduction && !decoded.scalar_destination && !decoded.fp_operation && !decoded.memory)begin
      rf_write=1;
      if(whole_move)rf_data=read_data[0];
      else case(operation)
        VI_VRGATHER,VI_VRGATHEREI16:rf_write=0;
        VI_VSLIDEUP:begin rf_write=!source_out_of_bounds;rf_data=read_data[0];end
        VI_VSLIDEDOWN:rf_data=source_out_of_bounds?0:read_data[0];
        VI_VSLIDE1UP:rf_data=index_q==0?scalar_a_q:read_data[0];
        VI_VSLIDE1DOWN:rf_data=index_q==vl_q-1?scalar_a_q:read_data[0];
        VI_VMV:begin rf_data=b;if(decoded.operation==V_VMV_S_X)begin rf_element=0;rf_write=index_q==0;end end
        VI_VCOMPRESS:begin rf_write=read_data[1][0];rf_element=packed_index_q;rf_data=read_data[0];end
        VI_VMSBF:rf_data=64'(!seen_q && !read_data[0][0]);
        VI_VMSOF:rf_data=64'(!seen_q && read_data[0][0]);
        VI_VMSIF:rf_data=64'(!seen_q);
        VI_VIOTA:rf_data=64'(packed_index_q);
        VI_VID:rf_data=64'(index_q);
        default:begin end
      endcase
    end
    if(int_result_valid_q && !int_result_meta_q.reduction)begin
      rf_write=1;rf_base=int_result_meta_q.base;rf_element=int_result_meta_q.element;
      rf_size=int_result_meta_q.size;rf_mask=int_result_meta_q.mask;rf_data=int_result_q;
      rf_packed=int_result_meta_q.packed_mode;rf_packed_data=int_wide_result_q;rf_bit_mask=int_write_mask_q;
    end
    if(state_q==DIV_WAIT && div_valid)begin
      rf_write=1;rf_base=int_meta_q.base;rf_element=int_meta_q.element;
      rf_size=int_meta_q.size;rf_mask=0;rf_data=div_result;
    end
    if(state_q==GATHER)begin rf_write=element_active;rf_data=source_out_of_bounds?0:read_data[0];end
    if(state_q==ELEMENT && decoded.fp_operation && fp_slide && element_active && index_q<effective_length && !fp_insert)begin
      rf_write=1;rf_data=read_data[0];
    end
    if(state_q==FP_WAIT && fp_valid && !fp_probe_q && !fp_exception && !reduction && !decoded.scalar_destination)begin
      rf_write=1;rf_data=fp_data;
    end
    if(state_q==FINISH && reduction && vl_q!=0)begin rf_write=1;rf_element=0;rf_data=accumulator_q;end
    if(state_q==MEM_WAIT && mem_valid && !mem_fault && !decoded.store)begin
      rf_write=1;rf_base=5'(mem_base);rf_element=index_q;rf_size=mem_size;rf_mask=0;rf_data=mem_result;
    end
  end
  // Every vector write crosses this boundary, including slides/FP/memory.
  // Source snapshots permit consecutive independent element writes at II=1.
  always_ff @(posedge clk_i)begin
    if(!rst_ni)rf_write_q<=0;
    else begin
      rf_write_q<=rf_write;
      if(rf_write)begin
        rf_base_q<=rf_base;rf_element_q<=rf_element;rf_size_q<=rf_size;
        rf_mask_q<=rf_mask;rf_data_q<=rf_data;
        rf_packed_q<=rf_packed;rf_packed_data_q<=rf_packed_data;rf_bit_mask_q<=rf_bit_mask;
      end
    end
  end
  always_ff @(posedge clk_i) begin
    if(!rst_ni)begin
      state_q<=IDLE;instruction_q<=0;scalar_a_q<=0;scalar_b_q<=0;
      vl_q<=0;vtype_q<=64'h8000000000000000;vstart_q<=0;vxrm_q<=0;vxsat_q<=0;
      index_q<=0;packed_index_q<=0;exception_q<=0;result_q<=0;accumulator_q<=0;gather_q<=0;
      seen_q<=0;state_dirty_o<=0;fp_enabled_q<=0;frm_q<=0;fp_probe_q<=0;flags_q<=0;
      cause_q<=0;tval_q<=0;field_q<=0;
      guest_q<=0;implicit_q<=0;
      int_valid_q<=0;int_result_valid_q<=0;int_operation_q<=VI_ILLEGAL;
      int_meta_q<='0;int_result_meta_q<='0;int_a_q<=0;int_b_q<=0;int_c_q<=0;
      int_carry_q<=0;int_wide_q<=0;int_rounding_q<=0;int_extension_q<=0;int_result_q<=0;int_saturated_q<=0;
      int_packed_a_q<=0;int_packed_b_q<=0;int_packed_c_q<=0;int_packed_carry_q<=0;
      int_wide_result_q<=0;int_write_mask_q<=0;
    end else begin
      state_dirty_o<=0;
      int_valid_q<=0;
      int_result_valid_q<=int_valid_q;
      if(int_valid_q)begin
        int_result_q<=alu_result[int_meta_q.sew];
        int_saturated_q<=int_meta_q.packed_mode?|(simd_saturated & int_meta_q.active_mask):alu_sat[int_meta_q.sew];
        int_wide_result_q<=packed_result;int_write_mask_q<=packed_write_mask;
        int_result_meta_q<=int_meta_q;
      end
      if(int_result_valid_q && int_saturated_q)vxsat_q<=1;
      if(state_q==ELEMENT && index_q<effective_length && integer_pipeline && (packed_integer || element_active))begin
        int_a_q<=a;int_b_q<=b;int_c_q<=c;int_operation_q<=operation;
        int_carry_q<=!instruction_q[25] && mask_bit;int_wide_q<=wide_source;
        int_rounding_q<=vxrm_q;int_extension_q<=extension_factor;
        int_meta_q.base<=instruction_q[11:7];int_meta_q.element<=index_q;
        int_meta_q.size<=destination_size;int_meta_q.sew<=sew_size;
        int_meta_q.mask<=mask_result;int_meta_q.reduction<=reduction;
        int_meta_q.packed_mode<=packed_integer;int_meta_q.active_mask<=packed_active;
        int_packed_a_q<=read_packed[0];int_packed_b_q<=packed_b;int_packed_c_q<=read_packed[2];
        int_packed_carry_q<=instruction_q[25]?16'b0:packed_mask;
      end
      if(csr_write_i && state_q==IDLE)begin
        case(csr_address_i)
          12'h008:vstart_q<=csr_data_i[6:0];
          12'h009:vxsat_q<=csr_data_i[0];
          12'h00a:vxrm_q<=csr_data_i[1:0];
          12'h00f:begin vxrm_q<=csr_data_i[2:1];vxsat_q<=csr_data_i[0];end
          default:begin end
        endcase
        state_dirty_o<=1;
      end
      case(state_q)
        IDLE:if(request_valid_i && request_ready_o)begin
          instruction_q<=instruction_i;scalar_a_q<=scalar_a_i;scalar_b_q<=scalar_b_i;
          index_q<={1'b0,vstart_q};packed_index_q<=0;exception_q<=0;result_q<=0;seen_q<=0;state_q<=CHECK;
          fp_enabled_q<=fp_state_enabled_i;frm_q<=frm_i;fp_probe_q<=0;flags_q<=0;
          cause_q<=2;tval_q<={32'b0,instruction_i};field_q<=0;
          guest_q<=0;implicit_q<=0;
        end
        CHECK:begin
          if(config_valid)begin vl_q<=config_vl;vtype_q<=config_type;vstart_q<=0;result_q<=config_vl;state_q<=RESULT;state_dirty_o<=1;end
          else if(!decoded.valid ||
              (decoded.fp_operation && (!fp_enabled_q || frm_q>4)) ||
              (!whole_move && !(decoded.memory && mem_whole) && vtype_q[63]) || !group_valid || (!special_operation && !alu_supported[sew_size]) ||
              (vstart_q!=0 && (reduction || decoded.operation==V_VCPOP_M || operation inside {VI_VFIRST,VI_VCOMPRESS,VI_VIOTA,VI_VMSBF,VI_VMSOF,VI_VMSIF})))begin
            exception_q<=1;state_q<=RESULT;
          end else if(decoded.operation==V_VMV_X_S)begin result_q<=sext(read_data[0],sew);state_q<=FINISH;end
          else if(decoded.fp_operation)begin
            if(reduction)accumulator_q<=read_data[1];
            fp_probe_q<=1;state_q<=FP_REQUEST;
          end else begin
            if(reduction)accumulator_q<=read_data[1];
            if(operation==VI_VFIRST)result_q<=64'hffffffffffffffff;
            state_q<=ELEMENT;
          end
        end
        ELEMENT:begin
          if(index_q>=effective_length)begin
            if(integer_pipeline)state_q<=INT_DRAIN;else state_q<=FINISH;
          end
          else if(packed_integer)begin
            int_valid_q<=|packed_active;index_q<=index_q+8'(packed_count);
          end
          else begin
            if(element_active)begin
              if(decoded.memory)state_q<=MEM_ISSUE;
              else if(decoded.fp_operation)begin
                if((decoded.operation==V_VFMV_S_F && index_q!=0) || (fp_slide && !fp_insert))index_q<=index_q+1'b1;
                else state_q<=FP_REQUEST;
              end
              else if(operation inside {VI_VRGATHER,VI_VRGATHEREI16})begin gather_q<=b;state_q<=GATHER;end
              else if(integer_pipeline)begin
                if(integer_divide)state_q<=DIV_REQUEST;
                else begin
                  int_valid_q<=1;
                  if(reduction)state_q<=INT_REDUCE_WAIT;
                  else index_q<=index_q+1'b1;
                end
              end
              else begin
                if(decoded.operation==V_VCPOP_M && read_data[0][0])result_q<=result_q+1'b1;
                if(operation==VI_VFIRST && read_data[0][0] && !seen_q)result_q<=64'(index_q);
                if(operation inside {VI_VMSBF,VI_VMSOF,VI_VMSIF,VI_VFIRST} && read_data[0][0])seen_q<=1;
                if(operation==VI_VIOTA && read_data[0][0] || operation==VI_VCOMPRESS && read_data[1][0])packed_index_q<=packed_index_q+1'b1;
                index_q<=index_q+1'b1;
              end
            end else index_q<=index_q+1'b1;
          end
        end
        INT_REDUCE_WAIT:if(int_result_valid_q)begin
          accumulator_q<=int_result_q;index_q<=index_q+1'b1;state_q<=ELEMENT;
        end
        // If writeback is the only remaining valid, the RF consumes it
        // on this edge. RESULT is visible after that edge, with no pending
        // writes. Do not add FINISH/WB_DRAIN bubbles to every ALU packet.
        INT_DRAIN:if(!int_valid_q && !int_result_valid_q)begin
          // Reduction still owns a final accumulator write in FINISH.
          if(reduction)state_q<=FINISH;
          else begin vstart_q<=0;state_dirty_o<=1;state_q<=RESULT;end
        end
        DIV_REQUEST:if(div_ready)state_q<=DIV_WAIT;
        DIV_WAIT:if(div_valid)begin index_q<=index_q+1'b1;state_q<=ELEMENT;end
        GATHER:begin index_q<=index_q+1'b1;state_q<=ELEMENT;end
        MEM_ISSUE:if(mem_ready)state_q<=MEM_WAIT;
        MEM_WAIT:if(mem_valid)begin
          if(mem_fault)begin
            state_dirty_o<=1;
            if(mem_ff && index_q!=0)begin vl_q<=64'(index_q);state_q<=FINISH;end
            else begin
              vstart_q<=index_q[6:0];exception_q<=1;cause_q<=mem_cause;tval_q<=mem_tval;state_q<=RESULT;
              guest_q<=mem_guest_address;implicit_q<=mem_implicit;
            end
          end else if(int'(field_q)+1==mem_fields)begin
            field_q<=0;index_q<=index_q+1'b1;state_q<=ELEMENT;
          end else begin field_q<=field_q+1'b1;state_q<=MEM_ISSUE;end
        end
        FP_REQUEST:if(fp_ready)state_q<=FP_WAIT;
        FP_WAIT:if(fp_valid)begin
          if(fp_exception)begin exception_q<=1;state_q<=RESULT;end
          else if(fp_probe_q)begin
            fp_probe_q<=0;
            if(decoded.operation==V_VFMV_F_S)state_q<=FP_REQUEST;
            else state_q<=ELEMENT;
          end else begin
            flags_q<=flags_q|fp_flags;
            if(reduction)accumulator_q<=fp_data;
            if(decoded.scalar_destination)begin result_q<=fp_data;state_q<=FINISH;end
            else begin index_q<=index_q+1'b1;state_q<=ELEMENT;end
          end
        end
        FINISH:begin
          vstart_q<=0;state_dirty_o<=1;
          // Reduction may enqueue its final write on this edge. Only that
          // case (or an already queued write) needs the explicit drain.
          state_q<=(rf_write || rf_write_q)?WB_DRAIN:RESULT;
        end
        WB_DRAIN:if(!rf_write_q)state_q<=RESULT;
        RESULT:if(response_ready_i)state_q<=IDLE;
        default:state_q<=IDLE;
      endcase
      if(rf_write)state_dirty_o<=1;
    end
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    response_valid_o && !response_ready_i |=> response_valid_o && $stable({response_data_o,response_exception_o,response_flags_o,response_cause_o,response_tval_o,response_guest_address_o,response_implicit_guest_access_o}));
  assert property(@(posedge clk_i) disable iff(!rst_ni)csr_write_i |-> state_q==IDLE);
`endif
endmodule

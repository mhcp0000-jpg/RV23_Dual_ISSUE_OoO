module rv_int_alu #(
  parameter int unsigned XLEN = 32,
  localparam int unsigned SHAMT_WIDTH = $clog2(XLEN)
) (
  input  logic [XLEN-1:0]             operand_a_i,
  input  logic [XLEN-1:0]             operand_b_i,
  input  rv_ooo_pkg::int_alu_op_e      operation_i,
  input  logic                        word_operation_i,
  output logic [XLEN-1:0]             result_o
);

  import rv_ooo_pkg::*;

  logic [XLEN-1:0] full_result;
  logic [31:0] word_result;
  logic [XLEN-1:0] add_result, sub_result;
  logic [XLEN-1:0] unsigned_word;
  logic [XLEN-1:0] bit_mask;
  logic [SHAMT_WIDTH-1:0] rotate_amount;
  integer clz_full,ctz_full,pop_full,clz_word,ctz_word,pop_word;
  assign unsigned_word=XLEN'(operand_a_i[31:0]);
  assign rotate_amount=operand_b_i[SHAMT_WIDTH-1:0];
  assign bit_mask=XLEN'(1)<<rotate_amount;

  // Four-bit carry-select slices calculate both carry cases in parallel.
  // Group carry is an AND/OR prefix of propagate/generate terms rather than
  // a full-width serial carry chain. The low 32 bits also serve ADDW/SUBW.
  function automatic logic [XLEN-1:0] sliced_add(
    input logic [XLEN-1:0] lhs,
    input logic [XLEN-1:0] rhs,
    input logic carry_in
  );
    localparam int GROUPS = XLEN/4;
    logic [GROUPS-1:0] propagate, generate_carry, carry;
    logic [4:0] sum0 [0:GROUPS-1];
    logic [4:0] sum1 [0:GROUPS-1];
    logic [GROUPS-1:0] prefix_p, prefix_g;
    for (int group = 0; group < GROUPS; group++) begin
      sum0[group] = {1'b0,lhs[group*4 +: 4]} +
                    {1'b0,rhs[group*4 +: 4]};
      sum1[group] = {1'b0,lhs[group*4 +: 4]} +
                    {1'b0,rhs[group*4 +: 4]} + 5'd1;
      propagate[group] = &(lhs[group*4 +: 4] ^ rhs[group*4 +: 4]);
      generate_carry[group] = sum0[group][4];
    end
    prefix_p = propagate;
    prefix_g = generate_carry;
    for (int stride = 1; stride < GROUPS; stride *= 2) begin
      prefix_g = prefix_g | (prefix_p & (prefix_g << stride));
      prefix_p = prefix_p & ((prefix_p << stride) |
                            ((GROUPS'(1) << stride) - GROUPS'(1)));
    end
    for (int group = 0; group < GROUPS; group++) begin
      if (group == 0)
        carry[group] = carry_in;
      else
        carry[group] = prefix_g[group-1] | (prefix_p[group-1] & carry_in);
      sliced_add[group*4 +: 4] = carry[group] ?
        sum1[group][3:0] : sum0[group][3:0];
    end
  endfunction

  assign add_result = sliced_add(operand_a_i, operand_b_i, 1'b0);
  assign sub_result = sliced_add(operand_a_i, ~operand_b_i, 1'b1);

  always_comb begin
    clz_full=XLEN;ctz_full=XLEN;pop_full=0;
    clz_word=32;ctz_word=32;pop_word=0;
    for(int i=0;i<XLEN;i++) begin
      if(operand_a_i[i]) begin
        clz_full=XLEN-1-i;
        if(ctz_full==XLEN) ctz_full=i;
        pop_full++;
      end
    end
    for(int i=0;i<32;i++) begin
      if(operand_a_i[i]) begin
        clz_word=31-i;
        if(ctz_word==32) ctz_word=i;
        pop_word++;
      end
    end
    case (operation_i)
      ALU_ADD:       full_result = add_result;
      ALU_SUB:       full_result = sub_result;
      ALU_SLT:       full_result = XLEN'($signed(operand_a_i) <
                                         $signed(operand_b_i));
      ALU_SLTU:      full_result = XLEN'(operand_a_i < operand_b_i);
      ALU_XOR:       full_result = operand_a_i ^ operand_b_i;
      ALU_OR:        full_result = operand_a_i | operand_b_i;
      ALU_AND:       full_result = operand_a_i & operand_b_i;
      ALU_SLL:       full_result = operand_a_i <<
                                   operand_b_i[SHAMT_WIDTH-1:0];
      ALU_SRL:       full_result = operand_a_i >>
                                   operand_b_i[SHAMT_WIDTH-1:0];
      ALU_SRA:       full_result = $unsigned($signed(operand_a_i) >>>
                                             operand_b_i[SHAMT_WIDTH-1:0]);
      ALU_COPY_SRC0: full_result = operand_a_i;
      ALU_COPY_SRC1: full_result = operand_b_i;
      ALU_SH1ADD:full_result=(operand_a_i<<1)+operand_b_i;
      ALU_SH2ADD:full_result=(operand_a_i<<2)+operand_b_i;
      ALU_SH3ADD:full_result=(operand_a_i<<3)+operand_b_i;
      ALU_ADDUW:full_result=unsigned_word+operand_b_i;
      ALU_SH1ADDUW:full_result=(unsigned_word<<1)+operand_b_i;
      ALU_SH2ADDUW:full_result=(unsigned_word<<2)+operand_b_i;
      ALU_SH3ADDUW:full_result=(unsigned_word<<3)+operand_b_i;
      ALU_SLLIUW:full_result=unsigned_word<<rotate_amount;
      ALU_ANDN:full_result=operand_a_i & ~operand_b_i;
      ALU_ORN:full_result=operand_a_i | ~operand_b_i;
      ALU_XNOR:full_result=~(operand_a_i ^ operand_b_i);
      ALU_MIN:full_result=$signed(operand_a_i)<$signed(operand_b_i) ? operand_a_i:operand_b_i;
      ALU_MINU:full_result=operand_a_i<operand_b_i ? operand_a_i:operand_b_i;
      ALU_MAX:full_result=$signed(operand_a_i)>$signed(operand_b_i) ? operand_a_i:operand_b_i;
      ALU_MAXU:full_result=operand_a_i>operand_b_i ? operand_a_i:operand_b_i;
      ALU_CLZ:full_result=XLEN'(clz_full);
      ALU_CTZ:full_result=XLEN'(ctz_full);
      ALU_CPOP:full_result=XLEN'(pop_full);
      ALU_SEXTB:full_result={{(XLEN-8){operand_a_i[7]}},operand_a_i[7:0]};
      ALU_SEXTH:full_result={{(XLEN-16){operand_a_i[15]}},operand_a_i[15:0]};
      ALU_ZEXTH:full_result=XLEN'(operand_a_i[15:0]);
      ALU_ROL:full_result=(operand_a_i<<rotate_amount) | (operand_a_i>>(XLEN-int'(rotate_amount)));
      ALU_ROR:full_result=(operand_a_i>>rotate_amount) | (operand_a_i<<(XLEN-int'(rotate_amount)));
      ALU_ORCB:begin
        for(int b=0;b<XLEN/8;b++) full_result[b*8+:8]={8{|operand_a_i[b*8+:8]}};
      end
      ALU_REV8:begin
        for(int b=0;b<XLEN/8;b++) full_result[b*8+:8]=operand_a_i[(XLEN/8-1-b)*8+:8];
      end
      ALU_BCLR:full_result=operand_a_i & ~bit_mask;
      ALU_BEXT:full_result=XLEN'(|(operand_a_i & bit_mask));
      ALU_BINV:full_result=operand_a_i ^ bit_mask;
      ALU_BSET:full_result=operand_a_i | bit_mask;
      ALU_CZERO_EQZ:full_result=operand_b_i==0 ? '0:operand_a_i;
      ALU_CZERO_NEZ:full_result=operand_b_i!=0 ? '0:operand_a_i;
      default:       full_result = '0;
    endcase

    case (operation_i)
      ALU_ADD:       word_result = add_result[31:0];
      ALU_SUB:       word_result = sub_result[31:0];
      ALU_SLT:       word_result = 32'($signed(operand_a_i[31:0]) <
                                       $signed(operand_b_i[31:0]));
      ALU_SLTU:      word_result = 32'(operand_a_i[31:0] < operand_b_i[31:0]);
      ALU_XOR:       word_result = operand_a_i[31:0] ^ operand_b_i[31:0];
      ALU_OR:        word_result = operand_a_i[31:0] | operand_b_i[31:0];
      ALU_AND:       word_result = operand_a_i[31:0] & operand_b_i[31:0];
      ALU_SLL:       word_result = operand_a_i[31:0] << operand_b_i[4:0];
      ALU_SRL:       word_result = operand_a_i[31:0] >> operand_b_i[4:0];
      ALU_SRA:       word_result =
        $unsigned($signed(operand_a_i[31:0]) >>> operand_b_i[4:0]);
      ALU_COPY_SRC0: word_result = operand_a_i[31:0];
      ALU_COPY_SRC1: word_result = operand_b_i[31:0];
      ALU_CLZ:word_result=32'(clz_word);
      ALU_CTZ:word_result=32'(ctz_word);
      ALU_CPOP:word_result=32'(pop_word);
      ALU_ROL:word_result=(operand_a_i[31:0]<<operand_b_i[4:0]) |
                          (operand_a_i[31:0]>>(32-int'(operand_b_i[4:0])));
      ALU_ROR:word_result=(operand_a_i[31:0]>>operand_b_i[4:0]) |
                          (operand_a_i[31:0]<<(32-int'(operand_b_i[4:0])));
      default:       word_result = '0;
    endcase

    if ((XLEN == 64) && word_operation_i)
      result_o = {{(XLEN-32){word_result[31]}}, word_result};
    else
      result_o = full_result;
  end

  initial begin : p_parameter_checks
    if ((XLEN != 32) && (XLEN != 64))
      $fatal(1, "Integer ALU XLEN must be 32 or 64");
  end

endmodule

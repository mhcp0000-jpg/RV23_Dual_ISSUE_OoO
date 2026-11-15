package rv_ooo_pkg;

  // Core configuration: the single source for default core/SoC elaboration.
  // These values select the default hardware profile. Measured timing and
  // CoreMark results belong to an exact source snapshot; see the HDD's
  // current release table rather than keeping a stale benchmark here.
  // They are compile/elaboration-time choices, NOT runtime CSR switches or
  // `ifdef macros. Explicit instance/tool parameter overrides take precedence.
  // Re-elaborate from RTL after editing; a cached netlist keeps its old choice.
  //
  // AGU: 1 enables the measured AGU-to-LSQ load bypass mode.
  // EARLY: 1 performs early LSQ load selection (unknown older stores still stall).
  // PAIR: 0 retains the measured issue-pair policy; 1 is a different policy.
  // BRANCH: 0 = IQ -> PRF -> BRU in one cycle (g_branch_fallthrough).
  //         1 = registered branch tags -> PRF -> BRU next cycle
  //             (g_branch_tag_pipeline); adds a branch issue/execute boundary.
  // DIV: 1 similarly registers DIV tags before reading operands; it does not
  //      change the divider's iteration algorithm or normal ALU latency.
  // CHECKPOINTS: number of branch rename recovery checkpoints.
  // fbc67e1 used literal top defaults AGU/BRANCH/DIV=0, but its published timing
  // and IPC run explicitly overrode them to 1. The defaults below remove that
  // ambiguity; old default-only synthesis results are NOT the same profile.
  localparam bit CORE_CFG_AGU_LOAD_BYPASS        = 1'b1;
  localparam bit CORE_CFG_EARLY_LOAD_SELECT      = 1'b1;
  localparam bit CORE_CFG_COMPATIBLE_PAIR_SELECT = 1'b0;
  localparam bit CORE_CFG_BRANCH_TAG_PIPELINE    = 1'b1;
  localparam bit CORE_CFG_DIV_TAG_PIPELINE       = 1'b1;
  // EXPERIMENT: operand-registered ALUs with execution-result preview wakeup.
  localparam bit CORE_CFG_INT_ISSUE_PIPELINE     = 1'b1;
  // Register head-only system results before WB. CSR writes still commit in
  // ROB order; normal ALU/load result latency and ROB completion stay direct.
  localparam bit CORE_CFG_SYSTEM_RESULT_PIPELINE = 1'b1;
  // Preserve WB/PRF/wakeup cycles; register only the four ROB completion
  // payloads. Head-only system operations wait for this in-flight result.
  localparam bit CORE_CFG_ROB_COMPLETION_PIPELINE = 1'b1;
  // Register only AGU store/address-fault completions (WB sources 5/6).
  // Normal load data/forwarding stays direct. Two entries isolate PMP->WB.
  localparam bit CORE_CFG_LSU_VALIDATION_PIPELINE = 1'b1;
  // Compute each IQ candidate's EA before selecting its LSU port. No extra
  // cycle; the unchanged AGU receives {base=selected EA, immediate=0}.
  // AGU DEPTH2 stores operands; finish EA/mask/alignment AFTER its existing
  // register, without adding an issue/update cycle. Keep tool defaults equal.
  localparam bit CORE_CFG_AGU_EA_PRECOMPUTE = 1'b0;
  localparam int unsigned CORE_CFG_BR_CHECKPOINTS = 8;
  // Fast FPU arithmetic stages. 6 places a register between mantissa-product/
  // exponent preparation and sticky alignment. FDIV/FSQRT remain iterative.
  // This is a real hardware boundary, not a synthesis-script-only override.
  localparam int unsigned CORE_CFG_FPU_LATENCY = 6;

  localparam int unsigned ARCH_INT_REGS = 32;
  localparam int unsigned ARCH_FP_REGS  = 32;
  localparam int unsigned FLEN          = 32;
  localparam int unsigned INST_BITS     = 32;
  localparam int unsigned ISSUE_WIDTH   = 2;
  localparam int unsigned COMMIT_WIDTH  = 2;
  // The active ROB window must be smaller than half of this modulo sequence
  // space so signed subtraction gives an unambiguous age comparison.
  localparam int unsigned ROB_SEQ_WIDTH = 8;

  // Baseline execution resources. These constants describe logical ports;
  // the physical PRF/SRAM implementation can still use banking or replication.
  localparam int unsigned INT_ALU_COUNT       = 2;
  localparam int unsigned BRANCH_UNIT_COUNT   = 1;
  localparam int unsigned INT_MUL_COUNT       = 1;
  localparam int unsigned INT_DIV_COUNT       = 1;
  localparam int unsigned LSU_PIPE_COUNT      = 2;
  localparam int unsigned AGU_COUNT           = 2;
  localparam int unsigned DTLB_LOOKUP_PORTS   = 2;
  localparam int unsigned DCACHE_CPU_PORTS    = 2;
  localparam int unsigned DCACHE_BANKS        = 2;
  localparam int unsigned FPU_CLUSTER_COUNT   = 1;
  localparam int unsigned FP_FMA_PIPE_COUNT   = 1;
  localparam int unsigned FP_DIVSQRT_COUNT    = 1;
  // Three source operands per two issue candidates plus two retire probes.
  localparam int unsigned INT_PRF_READ_PORTS  = 8;
  localparam int unsigned INT_PRF_WRITE_PORTS = 2;
  // Three FP source operands per two issue candidates plus two retire probes.
  localparam int unsigned FP_PRF_READ_PORTS   = 8;
  localparam int unsigned FP_PRF_WRITE_PORTS  = 2;

  typedef enum logic [2:0] {
    EXEC_PORT_INT0,
    EXEC_PORT_INT1,
    EXEC_PORT_MEM0,
    EXEC_PORT_MEM1,
    EXEC_PORT_FP
  } exec_port_e;

  typedef enum logic [2:0] {
    LSQ_STALL_NONE,
    LSQ_STALL_UNKNOWN_ADDR,
    LSQ_STALL_STORE_DATA,
    LSQ_STALL_PARTIAL_OVERLAP,
    LSQ_STALL_BANK_CONFLICT,
    LSQ_STALL_DEVICE_SERIALIZE
  } lsq_stall_reason_e;

  typedef enum logic [3:0] {
    FU_NONE,
    FU_INT,
    FU_BRANCH,
    FU_MUL,
    FU_DIV,
    FU_LOAD,
    FU_STORE,
    FU_FP,
    FU_CSR,
    FU_FENCE
  } fu_class_e;

  typedef enum logic [5:0] {
    ALU_ADD,
    ALU_SUB,
    ALU_SLT,
    ALU_SLTU,
    ALU_XOR,
    ALU_OR,
    ALU_AND,
    ALU_SLL,
    ALU_SRL,
    ALU_SRA,
    ALU_COPY_SRC0,
    ALU_COPY_SRC1,
    ALU_SH1ADD, ALU_SH2ADD, ALU_SH3ADD,
    ALU_ADDUW, ALU_SH1ADDUW, ALU_SH2ADDUW, ALU_SH3ADDUW, ALU_SLLIUW,
    ALU_ANDN, ALU_ORN, ALU_XNOR,
    ALU_MIN, ALU_MINU, ALU_MAX, ALU_MAXU,
    ALU_CLZ, ALU_CTZ, ALU_CPOP,
    ALU_SEXTB, ALU_SEXTH, ALU_ZEXTH,
    ALU_ROL, ALU_ROR, ALU_ORCB, ALU_REV8,
    ALU_BCLR, ALU_BEXT, ALU_BINV, ALU_BSET,
    ALU_CZERO_EQZ, ALU_CZERO_NEZ
  } int_alu_op_e;

  typedef struct packed {
    logic valid;
    int_alu_op_e operation;
    logic word_operation, uses_rs2;
    logic [5:0] immediate;
  } bitmanip_decode_t;

  // B 1.0 = Zba + Zbb + Zbs. Match complete encodings so reserved word,
  // unary and RV32 shamt[5] combinations keep their illegal-instruction trap.
  function automatic bitmanip_decode_t decode_bitmanip(
    input logic [31:0] insn, input int unsigned xlen,
    input bit has_b, input bit has_zicond
  );
    bitmanip_decode_t d;
    logic [9:0] key;
    d='0;d.operation=ALU_ADD;
    key={insn[31:25],insn[14:12]};
    d.uses_rs2=insn[6:0]==7'h33 || insn[6:0]==7'h3b;
    case(insn[6:0])
      7'h33: begin
        if(has_b) begin
          d.valid=1;
          case(key)
            {7'h10,3'h2}:d.operation=ALU_SH1ADD;
            {7'h10,3'h4}:d.operation=ALU_SH2ADD;
            {7'h10,3'h6}:d.operation=ALU_SH3ADD;
            {7'h20,3'h7}:d.operation=ALU_ANDN;
            {7'h20,3'h6}:d.operation=ALU_ORN;
            {7'h20,3'h4}:d.operation=ALU_XNOR;
            {7'h05,3'h4}:d.operation=ALU_MIN;
            {7'h05,3'h5}:d.operation=ALU_MINU;
            {7'h05,3'h6}:d.operation=ALU_MAX;
            {7'h05,3'h7}:d.operation=ALU_MAXU;
            {7'h30,3'h1}:d.operation=ALU_ROL;
            {7'h30,3'h5}:d.operation=ALU_ROR;
            {7'h24,3'h1}:d.operation=ALU_BCLR;
            {7'h24,3'h5}:d.operation=ALU_BEXT;
            {7'h34,3'h1}:d.operation=ALU_BINV;
            {7'h14,3'h1}:d.operation=ALU_BSET;
            {7'h04,3'h4}:begin
              d.operation=ALU_ZEXTH;d.uses_rs2=0;
              d.valid=xlen==32 && insn[24:20]==0;
            end
            default:d.valid=0;
          endcase
        end
        if(has_zicond && key=={7'h07,3'h5}) begin d.valid=1;d.operation=ALU_CZERO_EQZ;end
        if(has_zicond && key=={7'h07,3'h7}) begin d.valid=1;d.operation=ALU_CZERO_NEZ;end
      end
      7'h13: if(has_b) begin
        d.immediate=insn[25:20];
        if(insn[14:12]==1) begin
          d.valid=1;
          case(insn[31:20])
            12'h600:d.operation=ALU_CLZ;
            12'h601:d.operation=ALU_CTZ;
            12'h602:d.operation=ALU_CPOP;
            12'h604:d.operation=ALU_SEXTB;
            12'h605:d.operation=ALU_SEXTH;
            default:begin
              d.valid=xlen==64 || !insn[25];
              case(insn[31:26])
                6'h12:d.operation=ALU_BCLR;
                6'h1a:d.operation=ALU_BINV;
                6'h0a:d.operation=ALU_BSET;
                default:d.valid=0;
              endcase
            end
          endcase
        end else if(insn[14:12]==5) begin
          if(insn[31:20]==12'h287) begin d.valid=1;d.operation=ALU_ORCB;end
          else if(insn[31:20]==(xlen==64 ? 12'h6b8:12'h698)) begin d.valid=1;d.operation=ALU_REV8;end
          else if((xlen==64 || !insn[25]) && insn[31:26]==6'h18) begin d.valid=1;d.operation=ALU_ROR;end
          else if((xlen==64 || !insn[25]) && insn[31:26]==6'h12) begin d.valid=1;d.operation=ALU_BEXT;end
        end
      end
      7'h3b: if(has_b && xlen==64) begin
        d.valid=1;
        case(key)
          {7'h04,3'h0}:d.operation=ALU_ADDUW;
          {7'h10,3'h2}:d.operation=ALU_SH1ADDUW;
          {7'h10,3'h4}:d.operation=ALU_SH2ADDUW;
          {7'h10,3'h6}:d.operation=ALU_SH3ADDUW;
          {7'h30,3'h1}:begin d.operation=ALU_ROL;d.word_operation=1;end
          {7'h30,3'h5}:begin d.operation=ALU_ROR;d.word_operation=1;end
          {7'h04,3'h4}:begin d.operation=ALU_ZEXTH;d.uses_rs2=0;d.valid=insn[24:20]==0;end
          default:d.valid=0;
        endcase
      end
      7'h1b: if(has_b && xlen==64) begin
        d.immediate=insn[25:20];
        if(insn[14:12]==1) begin
          d.valid=1;d.word_operation=1;
          case(insn[31:20])
            12'h600:d.operation=ALU_CLZ;
            12'h601:d.operation=ALU_CTZ;
            12'h602:d.operation=ALU_CPOP;
            default:begin
              d.operation=ALU_SLLIUW;d.word_operation=0;
              d.valid=insn[31:26]==6'h02;
            end
          endcase
        end else if(key=={7'h30,3'h5}) begin
          d.valid=1;d.operation=ALU_ROR;d.word_operation=1;
        end
      end
      default:;
    endcase
    return d;
  endfunction

  typedef enum logic [3:0] {
    BR_NONE,
    BR_EQ,
    BR_NE,
    BR_LT,
    BR_GE,
    BR_LTU,
    BR_GEU,
    BR_JAL,
    BR_JALR
  } branch_op_e;

  typedef enum logic [1:0] {
    MUL_LOW,
    MUL_HIGH_SS,
    MUL_HIGH_SU,
    MUL_HIGH_UU
  } multiply_op_e;

  typedef enum logic [1:0] {
    DIV_SIGNED_QUOTIENT,
    DIV_UNSIGNED_QUOTIENT,
    DIV_SIGNED_REMAINDER,
    DIV_UNSIGNED_REMAINDER
  } divide_op_e;

  typedef enum logic [2:0] {
    CSR_CMD_NONE,
    CSR_CMD_WRITE,
    CSR_CMD_SET,
    CSR_CMD_CLEAR
  } csr_cmd_e;

  // Architectural privilege encoding is deliberately identical to the
  // privileged ISA CSR encoding.  PRIV_S remains reserved by the baseline
  // M/U core and becomes active when HAS_SMODE is enabled.
  typedef enum logic [1:0] {
    PRIV_U = 2'b00,
    PRIV_S = 2'b01,
    PRIV_M = 2'b11
  } privilege_e;

  typedef enum logic [2:0] {
    REG_NONE,
    REG_INT,
    REG_FP
  } reg_class_e;

  typedef enum logic [1:0] {
    INST_LEN_NONE,
    INST_LEN_16,
    INST_LEN_32
  } inst_len_e;

  typedef enum logic [5:0] {
    EXC_INST_ADDR_MISALIGNED = 6'd0,
    EXC_INST_ACCESS_FAULT    = 6'd1,
    EXC_ILLEGAL_INSTRUCTION  = 6'd2,
    EXC_BREAKPOINT           = 6'd3,
    EXC_LOAD_ADDR_MISALIGNED = 6'd4,
    EXC_LOAD_ACCESS_FAULT    = 6'd5,
    EXC_STORE_ADDR_MISALIGNED= 6'd6,
    EXC_STORE_ACCESS_FAULT   = 6'd7,
    EXC_ECALL_U              = 6'd8,
    EXC_ECALL_S              = 6'd9,
    EXC_ECALL_M              = 6'd11,
    EXC_INST_PAGE_FAULT      = 6'd12,
    EXC_LOAD_PAGE_FAULT      = 6'd13,
    EXC_STORE_PAGE_FAULT     = 6'd15,
    EXC_INST_GUEST_PAGE_FAULT= 6'd20,
    EXC_LOAD_GUEST_PAGE_FAULT= 6'd21,
    EXC_VIRTUAL_INSTRUCTION  = 6'd22,
    EXC_STORE_GUEST_PAGE_FAULT=6'd23
  } exception_code_e;

  typedef struct packed {
    logic       valid;
    logic       taken;
    logic       bimodal_taken;
    logic       global_taken;
    logic       use_global;
    logic       is_call;
    logic       is_return;
    logic [63:0] target;
    logic [10:0] global_history;
    logic [7:0] btb_index;
    logic [3:0] ras_pointer;
    logic [4:0] ras_count;
  } prediction_meta_t;

  typedef struct packed {
    logic       valid;
    fu_class_e  fu;
    reg_class_e src0_class;
    reg_class_e src1_class;
    reg_class_e src2_class;
    reg_class_e dst_class;
    logic [4:0] src0_arch;
    logic [4:0] src1_arch;
    logic [4:0] src2_arch;
    logic [4:0] dst_arch;
    logic       writes_dst;
    logic       is_serializing;
    logic       is_illegal;
  } decode_control_t;

  function automatic logic is_supported_xlen(input int unsigned xlen);
    return (xlen == 32) || (xlen == 64);
  endfunction

  function automatic logic [63:0] sign_extend_64(
    input logic [63:0] value,
    input int unsigned source_bits
  );
    logic [63:0] source_mask;
    if (source_bits == 0)
      return '0;
    if (source_bits >= 64)
      return value;
    source_mask = (64'h1 << source_bits) - 1'b1;
    return (value & source_mask) |
           ({64{value[source_bits-1]}} & ~source_mask);
  endfunction

endpackage

`timescale 1ns/1ps
module rv_pipeline_latency_tb;
  import rv_ooo_pkg::*;
  logic clk=0,rst_n=0;
  always #5 clk=~clk;
  logic mr=0,dr=0,fr=0,mready,dready,fready,mvalid,dvalid,fvalid;
  logic mw=0,dw=0;
  logic [63:0] ma=7,mb=3,da=100,db=7,fa=0,fb=0,fc=0,mdata,ddata,fdata;
  logic [31:0] insn=0;
  logic [4:0] fflags;
  logic fexception;
  divide_op_e dop=DIV_UNSIGNED_QUOTIENT;
  string label="";
  int cycle=0,started=0;
  rv_multiplier #(.XLEN(64)) mul(
    .clk_i(clk),.rst_ni(rst_n),.request_valid_i(mr),.request_ready_o(mready),
    .operand_a_i(ma),.operand_b_i(mb),.operation_i(MUL_LOW),.word_operation_i(mw),
    .sequence_i(8'd0),.destination_valid_i(1'b1),.destination_phys_i(7'd1),
    .flush_valid_i(1'b0),.flush_all_i(1'b0),.flush_sequence_i(8'd0),
    .result_valid_o(mvalid),.result_ready_i(1'b1),.result_o(mdata));
  rv_divider #(.XLEN(64)) div(
    .clk_i(clk),.rst_ni(rst_n),.request_valid_i(dr),.request_ready_o(dready),
    .operand_a_i(da),.operand_b_i(db),.operation_i(dop),.word_operation_i(dw),
    .request_rob_sequence_i(8'd0),.request_destination_valid_i(1'b1),.request_destination_phys_i(7'd1),
    .flush_valid_i(1'b0),.flush_all_i(1'b0),.flush_sequence_i(8'd0),
    .result_valid_o(dvalid),.result_ready_i(1'b1),.result_o(ddata));
  rv_fpu_rva23 fpu(
    .clk_i(clk),.rst_ni(rst_n),.request_valid_i(fr),.request_ready_o(fready),
    .instruction_i(insn),.operand_a_i(fa),.operand_b_i(fb),.operand_c_i(fc),
    .rounding_mode_i(3'd0),.frm_i(3'd0),.sequence_i(8'd0),
    .destination_valid_i(1'b1),.destination_class_i(REG_FP),.destination_phys_i(7'd1),
    .flush_valid_i(1'b0),.flush_all_i(1'b0),.flush_sequence_i(8'd0),
    .result_valid_o(fvalid),.result_ready_i(1'b1),.result_data_o(fdata),
    .result_fflags_o(fflags),.result_exception_valid_o(fexception));
  always @(posedge clk) if(rst_n) begin
    cycle++;
    if((mr&&mready)||(dr&&dready)||(fr&&fready)) started=cycle;
    if(mvalid||dvalid||fvalid) $display("PIPE_LAT %s cycles=%0d",label,cycle-started);
  end
  task automatic integer_case(input string name,input bit divide,input bit word_op,
      input logic [63:0] a,b,expected,input divide_op_e op=DIV_UNSIGNED_QUOTIENT);
    @(negedge clk);label=name;
    if(divide) begin
      while(!dready) @(negedge clk);
      da=a;db=b;dw=word_op;dop=op;dr=1;
      @(negedge clk);dr=0;
      while(!dvalid) @(negedge clk);
      if(ddata!==expected)$fatal(1,"DIV value %s %h",name,ddata);
    end else begin
      while(!mready) @(negedge clk);
      ma=a;mb=b;mw=word_op;mr=1;
      @(negedge clk);mr=0;
      while(!mvalid) @(negedge clk);
      if(mdata!==expected)$fatal(1,"MUL value %s",name);
    end
    @(negedge clk);
  endtask
  task automatic float_case(input string name,input logic[31:0] instruction,
      input logic[63:0] a,b,c,expected,input logic[4:0] flags=0);
    @(negedge clk);label=name;
    while(!fready) @(negedge clk);
    insn=instruction;fa=a;fb=b;fc=c;fr=1;
    @(negedge clk);fr=0;
    while(!fvalid) @(negedge clk);
    if(fdata!==expected||fflags!==flags||fexception)$fatal(1,"FP value %s data=%h flags=%h",name,fdata,fflags);
    @(negedge clk);
  endtask
  initial begin
    repeat(4) @(negedge clk);rst_n=1;
    integer_case("MUL",0,0,7,3,21);
    integer_case("MULW",0,1,64'hffffffff,2,64'hfffffffffffffffe);
    integer_case("DIVU",1,0,100,7,14);
    integer_case("DIVUW",1,1,100,7,14);
    integer_case("DIV_zero",1,0,100,0,64'hffffffffffffffff);
    integer_case("DIV_overflow",1,0,64'h8000000000000000,64'hffffffffffffffff,64'h8000000000000000,DIV_SIGNED_QUOTIENT);
    float_case("FADD_S",32'h001001d3,64'hffffffff3f800000,64'hffffffff40000000,0,64'hffffffff40400000);
    float_case("FADD_D",32'h021001d3,64'h3ff0000000000000,64'h4000000000000000,0,64'h4008000000000000);
    float_case("FMUL_S",32'h101001d3,64'hffffffff3f800000,64'hffffffff40000000,0,64'hffffffff40000000);
    float_case("FMUL_D",32'h121001d3,64'h3ff0000000000000,64'h4000000000000000,0,64'h4000000000000000);
    float_case("FMADD_S",32'h101001c3,64'hffffffff3f800000,64'hffffffff40000000,64'hffffffff40400000,64'hffffffff40a00000);
    float_case("FMADD_D",32'h121001c3,64'h3ff0000000000000,64'h4000000000000000,64'h4008000000000000,64'h4014000000000000);
    float_case("FCVT_S_W",32'hd00001d3,7,0,0,64'hffffffff40e00000);
    float_case("FDIV_S",32'h181001d3,64'hffffffff3f800000,64'hffffffff40400000,0,64'hffffffff3eaaaaab,1);
    float_case("FDIV_D",32'h1a1001d3,64'h3ff0000000000000,64'h4008000000000000,0,64'h3fd5555555555555,1);
    float_case("FSQRT_S",32'h580001d3,64'hffffffff40000000,0,0,64'hffffffff3fb504f3,1);
    float_case("FSQRT_D",32'h5a0001d3,64'h4000000000000000,0,0,64'h3ff6a09e667f3bcd,1);
    float_case("FDIV_D_zero",32'h1a1001d3,64'h3ff0000000000000,0,0,64'h7ff0000000000000,8);
    float_case("FSQRT_D_zero",32'h5a0001d3,0,0,0,0);
    $display("PASS pipeline unit latency values and flags");$finish;
  end
  initial begin #200000;$fatal(1,"pipeline latency timeout");end
endmodule

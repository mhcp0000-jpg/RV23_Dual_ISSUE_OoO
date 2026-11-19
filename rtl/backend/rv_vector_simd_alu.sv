// One 64-bit lane, subdivided into independent SEW elements. Widening,
// narrowing, reduction, permutation and divide use the owner's other paths.
module rv_vector_simd_lane(
  input rv_vector_decode_pkg::vector_integer_operation_e operation_i,
  input logic [1:0] sew_size_i,rounding_i,
  input logic [63:0] a_i,b_i,c_i,
  input logic [7:0] carry_i,
  output logic [63:0] result_o,
  output logic [7:0] saturated_o
);
  logic [3:0][63:0] results;
  logic [3:0][7:0] saturation;
  for(genvar size=0;size<4;size++)begin:g_size
    localparam int WIDTH=8<<size;
    localparam int ELEMENTS=64/WIDTH;
    logic [ELEMENTS-1:0] sat;
    for(genvar element=0;element<ELEMENTS;element++)begin:g_element
      logic [63:0] data;
      rv_vector_integer_alu #(.WIDTH(WIDTH),.EXTERNAL_DIVIDE(1)) u_alu(
        .operation_i,.operand_a_i(64'(a_i[element*WIDTH+:WIDTH])),
        .operand_b_i(64'(b_i[element*WIDTH+:WIDTH])),.accumulator_i(64'(c_i[element*WIDTH+:WIDTH])),
        .carry_i(carry_i[element]),.wide_source_i(1'b0),.rounding_i,.extension_factor_i(2'b0),
        .result_o(data),.saturated_o(sat[element]),.supported_o());
      assign results[size][element*WIDTH+:WIDTH]=data[WIDTH-1:0];
    end
    assign saturation[size]=8'(sat);
  end
  assign result_o=results[sew_size_i];
  assign saturated_o=saturation[sew_size_i];
endmodule

// Two physical 64-bit lanes: 2x64 / 4x32 / 8x16 / 16x8 integer elements.
// Operand and result registers are in rv_vector_engine, with per-batch metadata.
module rv_vector_simd_alu(
  input rv_vector_decode_pkg::vector_integer_operation_e operation_i,
  input logic [1:0] sew_size_i,rounding_i,
  input logic [127:0] a_i,b_i,c_i,
  input logic [15:0] carry_i,
  output logic [127:0] result_o,
  output logic [15:0] saturated_o
);
  logic [7:0] low_sat,high_sat;
  rv_vector_simd_lane u_lane0(.operation_i,.sew_size_i,.rounding_i,.a_i(a_i[63:0]),.b_i(b_i[63:0]),
    .c_i(c_i[63:0]),.carry_i(carry_i[7:0]),.result_o(result_o[63:0]),.saturated_o(low_sat));
  rv_vector_simd_lane u_lane1(.operation_i,.sew_size_i,.rounding_i,.a_i(a_i[127:64]),.b_i(b_i[127:64]),
    .c_i(c_i[127:64]),.carry_i(8'(carry_i>>(8>>sew_size_i))),.result_o(result_o[127:64]),.saturated_o(high_sat));
  always_comb case(sew_size_i)
    0:saturated_o={high_sat,low_sat};
    1:saturated_o={8'b0,high_sat[3:0],low_sat[3:0]};
    2:saturated_o={12'b0,high_sat[1:0],low_sat[1:0]};
    default:saturated_o={14'b0,high_sat[0],low_sat[0]};
  endcase
endmodule

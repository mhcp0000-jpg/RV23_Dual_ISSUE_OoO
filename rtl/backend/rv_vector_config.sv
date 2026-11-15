// RVV configuration result for a minimum VLEN128/ELEN64 implementation.
// Unsupported vtype and the reserved keep-vl ratio change select vill/vl=0.
module rv_vector_config #(
  parameter int unsigned VLEN=128,ELEN=64
)(
  input logic [31:0] instruction_i,
  input logic [63:0] avl_register_i,type_register_i,old_vl_i,old_type_i,
  output logic valid_o,
  output logic [63:0] vl_o,type_o,maximum_o
);
  import rv_vector_decode_pkg::*;
  vector_decode_t decoded;
  logic [63:0] new_type,avl;
  logic bad_type,keep_vl;
  int signed exponent,old_exponent;
  int unsigned sew,old_sew,capacity,old_capacity;
  always_comb begin
    decoded=decode_vector(instruction_i);
    valid_o=decoded.valid && decoded.configuration;
    new_type=0;avl=avl_register_i;keep_vl=0;
    if(decoded.operation==V_VSETVL) new_type=type_register_i;
    else if(decoded.operation==V_VSETIVLI) begin
      new_type=64'(instruction_i[29:20]);avl=64'(instruction_i[19:15]);
    end else new_type=64'(instruction_i[30:20]);
    if(decoded.operation!=V_VSETIVLI && instruction_i[19:15]==0) begin
      keep_vl=instruction_i[11:7]==0;
      avl=keep_vl?old_vl_i:64'hffffffffffffffff;
    end
    exponent=int'($signed(new_type[2:0]));
    old_exponent=int'($signed(old_type_i[2:0]));
    sew=8<<new_type[5:3];old_sew=8<<old_type_i[5:3];
    capacity=(exponent<0?(VLEN>>(-exponent)):(VLEN<<exponent))/sew;
    old_capacity=(old_exponent<0?(VLEN>>(-old_exponent)):(VLEN<<old_exponent))/old_sew;
    bad_type=|new_type[63:8] || new_type[5:3]>3 || new_type[2:0]==4 ||
      sew>ELEN || capacity==0 || (exponent<0 && sew>(ELEN>>(-exponent)));
    if(keep_vl && (old_type_i[63] || capacity!=old_capacity))bad_type=1;
    type_o=bad_type?64'h8000000000000000:new_type;
    maximum_o=bad_type?0:64'(capacity);
    vl_o=bad_type?0:(avl>64'(capacity)?64'(capacity):avl);
  end
  initial if(VLEN!=128 || ELEN!=64)$fatal(1,"Vector profile configuration is VLEN128/ELEN64");
endmodule

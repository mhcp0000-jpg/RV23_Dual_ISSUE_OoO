// One vector element's integer/fixed-point math. Vector register ownership,
// masks, restart, permutations and instruction legality belong to the engine.
module rv_vector_integer_alu #(
  parameter int unsigned WIDTH=32
)(
  input rv_vector_decode_pkg::vector_integer_operation_e operation_i,
  input logic [63:0] operand_a_i,operand_b_i,accumulator_i,
  input logic carry_i,wide_source_i,
  input logic [1:0] rounding_i,extension_factor_i,
  output logic [63:0] result_o,
  output logic saturated_o,supported_o
);
  import rv_vector_decode_pkg::*;
  localparam logic [127:0] MASK=(128'b1<<WIDTH)-1;
  localparam logic [127:0] WIDE_MASK=(128'b1<<(2*WIDTH))-1;
  localparam logic signed [127:0] MINIMUM=-$signed(128'b1<<(WIDTH-1));
  localparam logic signed [127:0] MAXIMUM=$signed((128'b1<<(WIDTH-1))-1);
  logic [127:0] a,b,wide_a,c,product,shifted;
  logic signed [127:0] sa,sb,swide_a,value;
  logic clip_signed,clip_unsigned,widen;
  int unsigned shift_amount,wide_shift,extension_width;
  bit found;
  function automatic logic signed [127:0] sign_extend(input logic[63:0] data,input int bits);
    logic [127:0] raw;
    raw=128'(data)&((128'b1<<bits)-1);
    return data[bits-1]?$signed(raw)-$signed(128'b1<<bits):$signed(raw);
  endfunction
  function automatic logic increment(input logic[127:0] data,input int amount,input logic[1:0] mode);
    logic sticky,lower;
    if(amount==0)return 0;
    sticky=|(data&((128'b1<<amount)-1));
    lower=|(data&((128'b1<<(amount-1))-1));
    case(mode)
      0:return data[amount-1];
      1:return data[amount-1] && (lower || data[amount]);
      2:return 0;
      default:return !data[amount] && sticky;
    endcase
  endfunction
  always_comb begin
    a=128'(operand_a_i)&MASK;b=128'(operand_b_i)&MASK;
    wide_a=128'(operand_a_i)&WIDE_MASK;c=128'(accumulator_i);
    sa=sign_extend(operand_a_i,WIDTH);sb=sign_extend(operand_b_i,WIDTH);
    // No legal ELEN64 operation consumes an EEW128 integer operand.
    swide_a=sign_extend(operand_a_i,WIDTH<64?2*WIDTH:64);
    product=0;shifted=0;value=0;clip_signed=0;clip_unsigned=0;widen=0;
    shift_amount=int'(operand_b_i)&(WIDTH-1);
    wide_shift=int'(operand_b_i)&(2*WIDTH-1);
    extension_width=WIDTH>>extension_factor_i;
    found=0;saturated_o=0;supported_o=1;
    case(operation_i)
      VI_VADD,VI_VREDSUM:value=$signed(a+b);
      VI_VSUB:value=$signed(a-b);
      VI_VRSUB:value=$signed(b-a);
      VI_VMINU,VI_VREDMINU:value=$signed(a<b?a:b);
      VI_VMIN,VI_VREDMIN:value=sa<sb?sa:sb;
      VI_VMAXU,VI_VREDMAXU:value=$signed(a>b?a:b);
      VI_VMAX,VI_VREDMAX:value=sa>sb?sa:sb;
      VI_VAND,VI_VREDAND,VI_VMAND:value=$signed(a&b);
      VI_VOR,VI_VREDOR,VI_VMOR:value=$signed(a|b);
      VI_VXOR,VI_VREDXOR,VI_VMXOR:value=$signed(a^b);
      VI_VANDN,VI_VMANDN:value=$signed(a&~b);
      VI_VMORN:value=$signed(a|~b);
      VI_VMNAND:value=$signed(~(a&b));
      VI_VMNOR:value=$signed(~(a|b));
      VI_VMXNOR:value=$signed(~(a^b));
      VI_VADC:value=$signed(a+b+128'(carry_i));
      VI_VMADC:value=$signed((a+b+128'(carry_i))>>WIDTH);
      VI_VSBC:value=$signed(a-b-128'(carry_i));
      VI_VMSBC:value=128'(a<b+128'(carry_i));
      VI_VMERGE:value=$signed(carry_i?b:a);
      VI_VMV:value=$signed(b);
      VI_VMSEQ:value=128'(a==b);
      VI_VMSNE:value=128'(a!=b);
      VI_VMSLTU:value=128'(a<b);
      VI_VMSLT:value=128'(sa<sb);
      VI_VMSLEU:value=128'(a<=b);
      VI_VMSLE:value=128'(sa<=sb);
      VI_VMSGTU:value=128'(a>b);
      VI_VMSGT:value=128'(sa>sb);
      VI_VSADDU:begin value=$signed(a+b);clip_unsigned=1;end
      VI_VSADD:begin value=sa+sb;clip_signed=1;end
      VI_VSSUBU:begin value=$signed(a)-$signed(b);clip_unsigned=1;end
      VI_VSSUB:begin value=sa-sb;clip_signed=1;end
      VI_VSLL:value=$signed(a<<shift_amount);
      VI_VSRL:value=$signed(a>>shift_amount);
      VI_VSRA:value=sa>>>shift_amount;
      VI_VSSRL:begin
        shifted=a>>shift_amount;
        value=$signed(shifted+128'(increment(a,shift_amount,rounding_i)));
      end
      VI_VSSRA:begin
        value=(sa>>>shift_amount)+$signed(128'(increment(128'(sa),shift_amount,rounding_i)));
      end
      VI_VNSRL:value=$signed(wide_a>>wide_shift);
      VI_VNSRA:value=swide_a>>>wide_shift;
      VI_VNCLIPU:begin
        value=$signed((wide_a>>wide_shift)+128'(increment(wide_a,wide_shift,rounding_i)));
        clip_unsigned=1;
      end
      VI_VNCLIP:begin
        value=(swide_a>>>wide_shift)+$signed(128'(increment(128'(swide_a),wide_shift,rounding_i)));
        clip_signed=1;
      end
      VI_VAADDU:value=$signed(((a+b)>>1)+128'(increment(a+b,1,rounding_i)));
      VI_VAADD:value=((sa+sb)>>>1)+$signed(128'(increment(128'(sa+sb),1,rounding_i)));
      VI_VASUBU:value=(($signed(a)-$signed(b))>>>1)+$signed(128'(increment(a-b,1,rounding_i)));
      VI_VASUB:value=((sa-sb)>>>1)+$signed(128'(increment(128'(sa-sb),1,rounding_i)));
      VI_VSMUL:begin
        product=128'(sa*sb);
        value=($signed(product)>>>(WIDTH-1))+$signed(128'(increment(product,WIDTH-1,rounding_i)));
        clip_signed=1;
      end
      VI_VDIVU:value=b==0?$signed(MASK):$signed(a/b);
      VI_VDIV:value=sb==0?$signed(MASK):sa/sb;
      VI_VREMU:value=b==0?$signed(a):$signed(a%b);
      VI_VREM:value=sb==0?sa:sa%sb;
      VI_VMUL,VI_VWMULU:begin product=a*b;value=$signed(product);widen=operation_i==VI_VWMULU;end
      VI_VMULHU:begin product=a*b;value=$signed(product>>WIDTH);end
      VI_VMULHSU:begin product=128'(sa*$signed(b));value=$signed(product)>>WIDTH;end
      VI_VMULH:begin product=128'(sa*sb);value=$signed(product)>>>WIDTH;end
      VI_VWMULSU:begin value=sa*$signed(b);widen=1;end
      VI_VWMUL:begin value=sa*sb;widen=1;end
      VI_VMACC:value=$signed(c+a*b);
      VI_VNMSAC:value=$signed(c-a*b);
      VI_VMADD:value=$signed(a+b*c);
      VI_VNMSUB:value=$signed(a-b*c);
      VI_VWMACCU:begin value=$signed(c+a*b);widen=1;end
      VI_VWMACC:begin value=$signed(c)+sa*sb;widen=1;end
      VI_VWMACCSU:begin value=$signed(c)+$signed(a)*sb;widen=1;end
      VI_VWMACCUS:begin value=$signed(c)+sa*$signed(b);widen=1;end
      VI_VWADDU:begin value=$signed((wide_source_i?wide_a:a)+b);widen=1;end
      VI_VWADD:begin value=(wide_source_i?swide_a:sa)+sb;widen=1;end
      VI_VWSUBU:begin value=$signed((wide_source_i?wide_a:a)-b);widen=1;end
      VI_VWSUB:begin value=(wide_source_i?swide_a:sa)-sb;widen=1;end
      VI_VWREDSUMU:begin value=$signed(c+a);widen=1;end
      VI_VWREDSUM:begin value=$signed(c)+sa;widen=1;end
      VI_VZEXT:begin
        value=$signed(a&((128'b1<<extension_width)-1));
        if(extension_width<8 || extension_factor_i==0)supported_o=0;
      end
      VI_VSEXT:begin
        value=sign_extend(operand_a_i,extension_width);
        if(extension_width<8 || extension_factor_i==0)supported_o=0;
      end
      VI_VBREV:for(int bit_index=0;bit_index<WIDTH;bit_index++)value[bit_index]=a[WIDTH-1-bit_index];
      VI_VBREV8:for(int bit_index=0;bit_index<WIDTH;bit_index++)
        value[bit_index]=a[(bit_index/8)*8+7-(bit_index%8)];
      VI_VREV8:for(int byte_index=0;byte_index<WIDTH/8;byte_index++)
        value[byte_index*8+:8]=a[(WIDTH/8-1-byte_index)*8+:8];
      VI_VCLZ:begin
        value=WIDTH;
        for(int bit_index=WIDTH-1;bit_index>=0;bit_index--) if(a[bit_index] && !found) begin
          value=WIDTH-1-bit_index;found=1;
        end
      end
      VI_VCTZ:begin
        value=WIDTH;
        for(int bit_index=0;bit_index<WIDTH;bit_index++) if(a[bit_index] && !found) begin value=bit_index;found=1;end
      end
      VI_VCPOP:for(int bit_index=0;bit_index<WIDTH;bit_index++)value+=128'(a[bit_index]);
      VI_VROL:value=$signed((a<<shift_amount)|(a>>(WIDTH-shift_amount)));
      VI_VROR:value=$signed((a>>shift_amount)|(a<<(WIDTH-shift_amount)));
      VI_VWSLL:begin value=$signed(a<<wide_shift);widen=1;end
      default:supported_o=0;
    endcase
    if(clip_signed) begin
      if(value>MAXIMUM)begin value=MAXIMUM;saturated_o=1;end
      if(value<MINIMUM)begin value=MINIMUM;saturated_o=1;end
    end
    if(clip_unsigned) begin
      if(value>$signed(MASK))begin value=$signed(MASK);saturated_o=1;end
      if(value<0)begin value=0;saturated_o=1;end
    end
    result_o=64'(128'(value)&(widen?WIDE_MASK:MASK));
    if(WIDTH==64 && (widen || operation_i inside {VI_VNSRL,VI_VNSRA,VI_VNCLIPU,VI_VNCLIP}))supported_o=0;
  end
  initial if(!(WIDTH inside {8,16,32,64}))$fatal(1,"Unsupported vector integer element width");
endmodule

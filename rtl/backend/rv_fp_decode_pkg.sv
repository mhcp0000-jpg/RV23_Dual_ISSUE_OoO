package rv_fp_decode_pkg;
  typedef struct packed {
    logic valid;
    logic [2:0] source_used,source_integer;
    logic destination_fp,rounding_used;
  } fp_decode_t;
  function automatic fp_decode_t decode_fp(
    input logic [31:0] instruction,
    input int unsigned xlen,
    input logic has_d,has_zfhmin,has_zfa
  );
    fp_decode_t d;
    logic [6:0] opcode;
    logic [4:0] family,rs2;
    logic [1:0] fmt;
    logic [2:0] f3;
    logic arithmetic_format,rm_ok,source_format;
    d='0;d.destination_fp=1;d.source_used=3'b001;
    opcode=instruction[6:0];family=instruction[31:27];rs2=instruction[24:20];
    fmt=instruction[26:25];f3=instruction[14:12];
    arithmetic_format=fmt==0 || (fmt==1 && has_d);
    source_format=rs2==0 || (rs2==1 && has_d) || (rs2==2 && has_zfhmin);
    rm_ok=f3<=4 || f3==7;
    if(opcode inside {7'h43,7'h47,7'h4b,7'h4f}) begin
      d.valid=arithmetic_format && rm_ok;d.source_used=3'b111;d.rounding_used=1;
    end else if(opcode==7'h53) case(family)
      0,1,2,3:begin d.valid=arithmetic_format && rm_ok;d.source_used=3'b011;d.rounding_used=1;end
      11:begin d.valid=arithmetic_format && rs2==0 && rm_ok;d.rounding_used=1;end
      4:begin d.valid=arithmetic_format && f3<=2;d.source_used=3'b011;end
      5:begin d.valid=arithmetic_format && (f3<=1 || (has_zfa && f3<=3));d.source_used=3'b011;end
      20:begin
        d.valid=arithmetic_format && (f3<=2 || (has_zfa && (f3==4 || f3==5)));
        d.source_used=3'b011;d.destination_fp=0;
      end
      24:begin
        d.valid=arithmetic_format && rs2<=(xlen==64?3:1) && rm_ok;
        if(has_zfa && fmt==1 && has_d && rs2==8 && f3==1) d.valid=1;
        d.destination_fp=0;d.rounding_used=1;
      end
      26:begin
        d.valid=arithmetic_format && rs2<=(xlen==64?3:1) && rm_ok;
        d.source_integer=3'b001;d.rounding_used=1;
      end
      8:begin
        d.valid=(arithmetic_format || (fmt==2 && has_zfhmin)) && source_format && rs2!={3'b0,fmt} && rm_ok;
        if(has_zfa && arithmetic_format && (rs2==4 || rs2==5) && rm_ok) d.valid=1;
        d.rounding_used=1;
      end
      28:begin
        d.destination_fp=0;
        d.valid=rs2==0 && ((arithmetic_format && f3==1) ||
          (f3==0 && (fmt==0 || (fmt==1 && has_d && xlen==64) || (fmt==2 && has_zfhmin))));
      end
      30:begin
        d.valid=f3==0 && rs2==0 && (fmt==0 || (fmt==1 && has_d && xlen==64) || (fmt==2 && has_zfhmin));
        d.source_integer=3'b001;
        if(has_zfa && arithmetic_format && rs2==1 && f3==0) begin
          d.valid=1;d.source_used=0;d.source_integer=0;
        end
      end
      default:begin end
    endcase
    return d;
  endfunction
endpackage

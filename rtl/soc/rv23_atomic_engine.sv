// Architectural head-only atomic transport. Addresses and PMP permissions must
// be validated before request acceptance. No speculative request may enter.
// All data uses main AXI exclusive transactions; concurrent debug writes are
// serialized by the SRAM's monitor, so AMO retries cannot lose an intervening write.
module rv23_atomic_engine #(
  parameter int unsigned ID_WIDTH=4,
  parameter logic [ID_WIDTH-1:0] AXI_ID={ID_WIDTH{1'b1}}
) (
  input logic clk_i,rst_ni,
  input logic request_valid_i,
  output logic request_ready_o,
  input logic [31:0] request_address_i,
  input logic [63:0] request_operand_i,
  input logic [4:0] request_operation_i,
  input logic request_word_i,
  input logic request_privileged_i,
  input logic clear_reservation_i,
  input logic write_snoop_i,
  input logic [31:0] write_snoop_address_i,
  output logic reservation_valid_o,
  output logic idle_o,
  output logic response_valid_o,
  input logic response_ready_i,
  output logic [63:0] response_data_o,
  output logic response_exception_o,
  output logic [5:0] response_cause_o,
  rv_axi4_if.master axi_m
);
  import rv_soc_pkg::*;
  localparam logic [4:0] LR=5'b00010,SC=5'b00011;
  typedef enum logic [2:0] {IDLE,READ_ADDR,READ_DATA,WRITE_ADDR,WRITE_DATA,
                           WRITE_RESP,RESULT} state_t;
  state_t state_q;
  logic [31:0] address_q,reservation_address_q;
  logic [63:0] operand_q,old_q,write_q,result_q;
  logic [4:0] operation_q;
  logic word_q,privileged_q,exception_q;
  logic [5:0] cause_q;
  logic reservation_q,reservation_word_q;
  logic [63:0] selected_read,amo_value;
  logic snoop_hit;

  function automatic logic valid_operation(input logic [4:0] op);
    case(op)
      LR,SC,5'b00000,5'b00001,5'b00100,5'b01000,5'b01100,
      5'b10000,5'b10100,5'b11000,5'b11100: return 1;
      default:return 0;
    endcase
  endfunction
  function automatic logic [63:0] calculate(
    input logic [63:0] old_value,operand,
    input logic [4:0] op,input logic word_op
  );
    logic [63:0] a,b,r;
    a=word_op ? {{32{old_value[31]}},old_value[31:0]} : old_value;
    b=word_op ? {{32{operand[31]}},operand[31:0]} : operand;
    case(op)
      5'b00000:r=a+b;
      5'b00001:r=b;
      5'b00100:r=a^b;
      5'b01000:r=a|b;
      5'b01100:r=a&b;
      5'b10000:r=($signed(a)<$signed(b))?a:b;
      5'b10100:r=($signed(a)>$signed(b))?a:b;
      5'b11000:r=(a<b)?a:b;
      5'b11100:r=(a>b)?a:b;
      default:r=0;
    endcase
    // Sign extension preserves ordering of unsigned 32-bit operands when both
    // are extended the same way; only low 32 bits are written for AMO.W.
    return r;
  endfunction
  assign snoop_hit=write_snoop_i &&
    write_snoop_address_i[31:6]==reservation_address_q[31:6];
  assign reservation_valid_o=reservation_q && !clear_reservation_i && !snoop_hit;
  assign request_ready_o=state_q==IDLE;
  assign idle_o=state_q==IDLE;
  assign response_valid_o=state_q==RESULT;
  assign response_data_o=result_q;
  assign response_exception_o=exception_q;
  assign response_cause_o=cause_q;
  assign selected_read=word_q ? (axi_m.r_data >> (address_q[2]*32)) : axi_m.r_data;
  assign amo_value=calculate(selected_read,operand_q,operation_q,word_q);

  always_comb begin
    axi_m.aw_id=AXI_ID;axi_m.aw_addr=address_q;axi_m.aw_len=0;
    axi_m.aw_size=word_q?2:3;axi_m.aw_burst=1;axi_m.aw_lock=1;
    axi_m.aw_prot={2'b0,privileged_q};axi_m.aw_cache=0;axi_m.aw_qos=0;
    axi_m.aw_valid=state_q==WRITE_ADDR;
    axi_m.w_data=word_q ? (write_q << (address_q[2]*32)) : write_q;
    axi_m.w_strb=word_q ? (8'h0f << (address_q[2]*4)) : 8'hff;
    axi_m.w_last=1;axi_m.w_valid=state_q==WRITE_DATA;
    axi_m.b_ready=state_q==WRITE_RESP;
    axi_m.ar_id=AXI_ID;axi_m.ar_addr=address_q;axi_m.ar_len=0;
    axi_m.ar_size=word_q?2:3;axi_m.ar_burst=1;axi_m.ar_lock=1;
    axi_m.ar_prot={2'b0,privileged_q};axi_m.ar_cache=0;axi_m.ar_qos=0;
    axi_m.ar_valid=state_q==READ_ADDR;
    axi_m.r_ready=state_q==READ_DATA;
  end
  always_ff @(posedge clk_i) begin
    if(!rst_ni) begin
      state_q<=IDLE;reservation_q<=0;reservation_word_q<=0;
      address_q<=0;operand_q<=0;old_q<=0;write_q<=0;result_q<=0;
      operation_q<=0;word_q<=0;privileged_q<=0;exception_q<=0;cause_q<=0;
    end else begin
      if(clear_reservation_i || snoop_hit) reservation_q<=0;
      case(state_q)
        IDLE:if(request_valid_i) begin
          address_q<=request_address_i;operand_q<=request_operand_i;
          operation_q<=request_operation_i;word_q<=request_word_i;
          privileged_q<=request_privileged_i;
          result_q<=0;exception_q<=0;cause_q<=0;
          // Every SC attempt consumes the hart's reservation, even on faults.
          // AMOs use this master's monitor and therefore also abandon old LR.
          reservation_q<=0;
          if(!valid_operation(request_operation_i)) begin
            exception_q<=1;cause_q<=2;state_q<=RESULT;
          end else if((request_address_i & (request_word_i?32'd3:32'd7))!=0) begin
            exception_q<=1;cause_q<=(request_operation_i==LR)?4:6;state_q<=RESULT;
          end else if(!rv_soc_pkg::addr_in_region(request_address_i,
              rv23_pkg::SRAM_BASE,rv_soc_pkg::size_kb_to_bytes(rv23_pkg::SRAM_KB))) begin
            exception_q<=1;cause_q<=(request_operation_i==LR)?5:7;state_q<=RESULT;
          end else if(request_operation_i==SC) begin
            if(reservation_valid_o && reservation_address_q==request_address_i &&
               reservation_word_q==request_word_i) begin
              write_q<=request_operand_i;state_q<=WRITE_ADDR;
            end else begin result_q<=1;state_q<=RESULT;end
          end else state_q<=READ_ADDR;
        end
        READ_ADDR:if(axi_m.ar_ready) state_q<=READ_DATA;
        READ_DATA:if(axi_m.r_valid) begin
          if(axi_m.r_resp[1] || axi_m.r_id!=AXI_ID || !axi_m.r_last ||
             (operation_q!=LR && axi_m.r_resp!=AXI_RESP_EXOKAY)) begin
            exception_q<=1;cause_q<=(operation_q==LR)?5:7;state_q<=RESULT;
          end else begin
            old_q<=word_q?{{32{selected_read[31]}},selected_read[31:0]}:selected_read;
            if(operation_q==LR) begin
              result_q<=word_q?{{32{selected_read[31]}},selected_read[31:0]}:selected_read;
              reservation_q<=axi_m.r_resp==AXI_RESP_EXOKAY && !clear_reservation_i;
              reservation_address_q<=address_q;reservation_word_q<=word_q;
              state_q<=RESULT;
            end else begin write_q<=amo_value;state_q<=WRITE_ADDR;end
          end
        end
        WRITE_ADDR:if(axi_m.aw_ready) state_q<=WRITE_DATA;
        WRITE_DATA:if(axi_m.w_ready) state_q<=WRITE_RESP;
        WRITE_RESP:if(axi_m.b_valid) begin
          if(axi_m.b_resp[1] || axi_m.b_id!=AXI_ID) begin
            exception_q<=1;cause_q<=7;state_q<=RESULT;
          end else if(operation_q==SC) begin
            result_q<=axi_m.b_resp==AXI_RESP_EXOKAY?0:1;state_q<=RESULT;
          end else if(axi_m.b_resp==AXI_RESP_EXOKAY) begin
            result_q<=old_q;state_q<=RESULT;
          end else state_q<=READ_ADDR;
        end
        RESULT:if(response_ready_i) state_q<=IDLE;
        default:state_q<=IDLE;
      endcase
    end
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    response_valid_o && !response_ready_i |=> response_valid_o &&
      $stable({response_data_o,response_exception_o,response_cause_o}));
`endif
endmodule

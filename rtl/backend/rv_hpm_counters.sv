// Zihpm/Sscofpmf event counters. Actual execution mode controls filtering;
// MPRV changes data privilege only. Events are platform-defined and documented
// in HPM_COUNTERS.md. Unsupported selectors and absent counters read zero.
module rv_hpm_counters #(
  parameter int unsigned XLEN=64,COUNTERS=4,
  parameter bit HAS_SMODE=1,HAS_H=1
)(
  input logic clk_i,rst_ni,
  input logic [1:0] privilege_i,
  input logic virtual_i,
  input logic [1:0] retire_count_i,
  input logic [31:0] inhibit_i,
  input logic write_valid_i,
  input logic [11:0] write_address_i,
  input logic [XLEN-1:0] write_data_i,
  input logic pending_write_i,pending_data_i,
  output logic pending_o,
  output logic [31:0] counter_mask_o,overflow_o,
  output wire [31:0][63:0] counter_o,event_o
);
  logic [31:0] request_overflow;
  for(genvar index=0;index<32;index++)begin:g_counter
    if(index>=3 && index<3+COUNTERS)begin:g_implemented
      logic [63:0] count_q,event_q;
      logic [64:0] next_count;
      logic [1:0] increment;
      logic filtered,counter_write,event_write;
      logic [63:0] event_warl;
      assign counter_mask_o[index]=1;
      assign counter_o[index]=count_q;assign event_o[index]=event_q;
      assign overflow_o[index]=event_q[63];
      assign counter_write=write_valid_i &&
        (write_address_i==12'(12'hb00+index) || (XLEN==32 && write_address_i==12'(12'hb80+index)));
      assign event_write=write_valid_i &&
        (write_address_i==12'(12'h320+index) || (XLEN==32 && write_address_i==12'(12'h720+index)));
      always_comb begin
        filtered=privilege_i==3?event_q[62]:
          (privilege_i==1?(virtual_i?event_q[59]:event_q[61]):(virtual_i?event_q[58]:event_q[60]));
        increment=0;
        if(!inhibit_i[index] && !filtered)case(event_q[57:0])
          58'd1:increment=1;                          // cycles in selected modes
          58'd2:increment=retire_count_i;             // retired instructions
          58'd3:increment={1'b0,retire_count_i==2};    // dual retirement cycles
          58'd4:increment={1'b0,retire_count_i==0};    // no retirement cycles
          default:begin end
        endcase
        next_count={1'b0,count_q}+65'(increment);
        event_warl=64'(write_data_i);
        if(XLEN==32 && write_address_i==12'(12'h720+index))event_warl={32'(write_data_i),event_q[31:0]};
        else if(XLEN==32)event_warl={event_q[63:32],32'(write_data_i)};
        if(event_warl[57:0]>4)event_warl[57:0]=0;
        if(!HAS_SMODE)event_warl[61]=0;
        if(!HAS_H)event_warl[59:58]=0;
      end
      assign request_overflow[index]=next_count[64] && !event_q[63] && !counter_write && !event_write;
      always_ff @(posedge clk_i)begin
        if(!rst_ni)begin count_q<=0;event_q<=0;end
        else begin
          count_q<=next_count[63:0];
          if(counter_write)begin
            if(XLEN==64)count_q<=64'(write_data_i);
            else if(write_address_i==12'(12'hb80+index))count_q<={32'(write_data_i),count_q[31:0]};
            else count_q<={count_q[63:32],32'(write_data_i)};
          end
          if(next_count[64] && !counter_write && !event_write)event_q[63]<=1;
          if(event_write)event_q<=event_warl;
        end
      end
    end else begin:g_absent
      assign counter_mask_o[index]=0;assign counter_o[index]=0;assign event_o[index]=0;
      assign overflow_o[index]=0;assign request_overflow[index]=0;
    end
  end
  always_ff @(posedge clk_i)begin
    if(!rst_ni)pending_o<=0;
    else if(|request_overflow)pending_o<=1;
    else if(pending_write_i)pending_o<=pending_data_i;
  end
  initial begin
    if(COUNTERS>29 || !(XLEN inside {32,64}))$fatal(1,"Invalid HPM configuration");
  end
endmodule

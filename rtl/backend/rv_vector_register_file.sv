// Architectural VLEN128 vector storage and per-operation source snapshot.
// Payload is intentionally not reset. Acceptance captures old source values,
// so in-place widening, narrowing and permutations cannot consume new writes.
module rv_vector_register_file (
  input logic clk_i,rst_ni,capture_i,
  input logic [2:0][4:0] read_base_i,
  input logic [2:0][7:0] read_element_i,
  input logic [2:0][1:0] read_size_i,
  input logic [2:0] read_mask_i,
  output logic [2:0][63:0] read_data_o,
  output logic [2:0] read_valid_o,
  input logic [6:0] mask_element_i,
  output logic mask_o,
  input logic write_valid_i,
  input logic [4:0] write_base_i,
  input logic [7:0] write_element_i,
  input logic [1:0] write_size_i,
  input logic write_mask_i,
  input logic [63:0] write_data_i
);
  logic [127:0] live_q[32],snapshot_q[32];
  logic snapshot_valid_q;
  int unsigned write_register,write_offset,write_bits;
  logic [127:0] write_mask,write_data;
  assign mask_o=snapshot_valid_q && snapshot_q[0][mask_element_i];
  always_comb begin
    for(int port_index=0;port_index<3;port_index++) begin
      int unsigned bits,offset,register_index;
      bits=read_mask_i[port_index]?1:(8<<read_size_i[port_index]);
      offset=int'(read_element_i[port_index])*bits;
      register_index=int'(read_base_i[port_index])+offset/128;
      read_valid_o[port_index]=snapshot_valid_q && register_index<32;
      read_data_o[port_index]=0;
      if(read_valid_o[port_index])
        read_data_o[port_index]=64'(snapshot_q[register_index]>>(offset%128)) &
          64'((128'b1<<bits)-1);
    end
    write_bits=write_mask_i?1:(8<<write_size_i);
    write_offset=int'(write_element_i)*write_bits;
    write_register=int'(write_base_i)+write_offset/128;
    write_mask=((128'b1<<write_bits)-1)<<(write_offset%128);
    write_data=(128'(write_data_i)&((128'b1<<write_bits)-1))<<(write_offset%128);
  end
  always_ff @(posedge clk_i) begin
    if(!rst_ni)snapshot_valid_q<=0;
    else begin
      if(capture_i) begin
        snapshot_valid_q<=1;
        for(int register_index=0;register_index<32;register_index++)snapshot_q[register_index]<=live_q[register_index];
      end
      if(write_valid_i && write_register<32)
        for(int register_index=0;register_index<32;register_index++)
          if(write_register==register_index)
            live_q[register_index]<=(live_q[register_index]&~write_mask)|write_data;
    end
  end
`ifndef SYNTHESIS
  assert property(@(posedge clk_i) disable iff(!rst_ni)
    write_valid_i |-> write_register<32 && (write_offset%128)+write_bits<=128);
`endif
endmodule

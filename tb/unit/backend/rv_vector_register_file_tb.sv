`timescale 1ns/1ps
module rv_vector_register_file_tb;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,capture=0,write_enable=0,write_mask=0;
  logic [2:0][4:0] bases=0;
  logic [2:0][7:0] elements=0;
  logic [2:0][1:0] sizes=0;
  logic [2:0] masks=0,valid;
  logic [2:0][63:0] data;
  logic [6:0] mask_element=0;
  logic mask;
  logic [4:0] wb=0;
  logic [7:0] we=0;
  logic [1:0] ws=0;
  logic [63:0] wd=0;
  logic [127:0] reference[32];
  int checks=0;
  rv_vector_register_file dut(.clk_i(clk),.rst_ni(rst_n),.capture_i(capture),
    .read_base_i(bases),.read_element_i(elements),.read_size_i(sizes),.read_mask_i(masks),
    .read_data_o(data),.read_valid_o(valid),.mask_element_i(mask_element),.mask_o(mask),
    .write_valid_i(write_enable),.write_base_i(wb),.write_element_i(we),.write_size_i(ws),
    .write_mask_i(write_mask),.write_data_i(wd));
  task automatic snapshot();
    @(negedge clk);capture=1;@(negedge clk);capture=0;
  endtask
  initial begin
    repeat(3)@(negedge clk);rst_n=1;
    for(int r=0;r<32;r++) for(int word_index=0;word_index<2;word_index++) begin
      wb=5'(r);we=8'(word_index);ws=3;wd=64'h8123456789abcdef^64'(r*131+word_index*79);
      reference[r][word_index*64+:64]=wd;write_enable=1;
      @(negedge clk);
    end
    write_enable=0;snapshot();
    // All element sizes, all register bases, cross-register group addressing.
    for(int s=0;s<4;s++) for(int r=0;r<32;r++) for(int e=0;e<128;e++) begin
      int reg_index,offset,bits;
      logic[63:0] expected;
      bits=8<<s;reg_index=r+(e*bits)/128;offset=(e*bits)%128;
      bases[0]=5'(r);elements[0]=8'(e);sizes[0]=2'(s);#1;
      if(valid[0] !== (reg_index<32))$fatal(1,"out-of-range group read was not detected");
      if(reg_index<32) begin
        expected=64'(reference[reg_index]>>offset)&64'((128'b1<<bits)-1);
        if(data[0]!==expected)$fatal(1,"element mapping s%0d r%0d e%0d got%h want%h",s,r,e,data[0],expected);
      end
      checks++;
    end
    // Live in-place writes must not modify the captured source operands/mask.
    bases[0]=0;elements[0]=0;sizes[0]=3;
    wb=0;we=0;ws=3;wd=0;write_enable=1;
    @(negedge clk);write_enable=0;#1;
    if(data[0]!==reference[0][63:0])$fatal(1,"source snapshot changed during in-place update");
    for(int bit_index=0;bit_index<128;bit_index++) begin
      mask_element=7'(bit_index);#1;
      if(mask!==reference[0][bit_index])$fatal(1,"mask snapshot changed during write");
    end
    snapshot();#1;if(data[0]!==0)$fatal(1,"new operation did not capture updated destination");
    // A mask result writes one bit, preserving adjacent bits and other bytes.
    wb=0;we=127;write_mask=1;wd=1;write_enable=1;
    @(negedge clk);write_enable=0;reference[0][63:0]=0;reference[0][127]=1;
    snapshot();
    masks[1]=1;bases[1]=0;
    for(int bit_index=0;bit_index<128;bit_index++) begin
      elements[1]=8'(bit_index);#1;
      if(data[1]!==64'(reference[0][bit_index]))$fatal(1,"mask write corrupted adjacent state");
    end
    $display("PASS rv_vector_register_file_tb element checks=%0d plus overlap/mask ownership",checks);$finish;
  end
endmodule

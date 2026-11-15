`timescale 1ns/1ps
module rv_vector_config_tb;
  logic [31:0] instruction;
  logic [63:0] avl,vtype,old_vl,old_type,vl,result_type,maximum;
  logic valid;
  int checks=0;
  rv_vector_config dut(.instruction_i(instruction),.avl_register_i(avl),.type_register_i(vtype),
    .old_vl_i(old_vl),.old_type_i(old_type),.valid_o(valid),.vl_o(vl),.type_o(result_type),.maximum_o(maximum));
  task automatic check(input logic[63:0] expected_vl,expected_type,expected_maximum);
    #1;
    if(!valid || vl!==expected_vl || result_type!==expected_type || maximum!==expected_maximum)
      $fatal(1,"vset %h avl%h type%h got vl%0d type%h max%0d expected vl%0d type%h max%0d",
        instruction,avl,vtype,vl,result_type,maximum,expected_vl,expected_type,expected_maximum);
    checks++;
  endtask
  initial begin
    int expected_maximum;
    bit type_supported;
    avl=0;vtype=0;old_vl=7;old_type=0;instruction=32'h80b57657; // vsetvl a2,a0,a1
    for(int mul_code=0;mul_code<8;mul_code++) for(int sew_code=0;sew_code<8;sew_code++) begin
      // Independent table for mandatory ELEN64 fractional type combinations.
      type_supported=(mul_code<=3 && sew_code<=3) ||
        (mul_code==7 && sew_code<=2) || (mul_code==6 && sew_code<=1) || (mul_code==5 && sew_code==0);
      expected_maximum=0;
      if(type_supported) case(mul_code)
        0:expected_maximum=16>>sew_code;
        1:expected_maximum=32>>sew_code;
        2:expected_maximum=64>>sew_code;
        3:expected_maximum=128>>sew_code;
        5:expected_maximum=2;
        6:expected_maximum=4>>sew_code;
        7:expected_maximum=8>>sew_code;
      endcase
      for(int policy=0;policy<4;policy++) for(int n=0;n<260;n++) begin
        vtype=64'((policy<<6)|(sew_code<<3)|mul_code);avl=64'(n);
        if(type_supported)check(n>expected_maximum?64'(expected_maximum):64'(n),vtype,64'(expected_maximum));
        else check(0,64'h8000000000000000,0);
      end
    end
    for(int bit_index=8;bit_index<64;bit_index++) begin
      vtype=64'b1<<bit_index;avl=1;check(0,64'h8000000000000000,0);
    end
    // x0 AVL chooses maximum; x0/x0 preserves VL for an unchanged ratio.
    instruction=32'h80b07657;vtype=0;avl=0;check(16,0,16);
    instruction=32'h80b07057;old_vl=7;old_type=0;vtype=0;check(7,0,16);
    vtype=8;check(0,64'h8000000000000000,0); // reserved ratio change
    instruction=32'hc101f657;check(3,16,4);  // vsetivli a2,3,e32,m1
    instruction=32'h01057657;avl=2;vtype=-1;check(2,16,4); // vsetvli immediate wins
    instruction=0;#1;if(valid)$fatal(1,"non-configuration opcode accepted");
    $display("PASS rv_vector_config_tb checks=%0d",checks);$finish;
  end
endmodule

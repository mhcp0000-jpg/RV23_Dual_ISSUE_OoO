`timescale 1ns/1ps
module rv_hypervisor_stateen_tb #(parameter bit HAS_SMSTATEEN=0);
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,valid=0,write=0,selected,exception,env_exception,virtual_mode=0;
  logic [1:0] privilege=3;
  logic [11:0] address=0;
  logic [63:0] data=0,result;
  logic [5:0] cause,env_cause;
  int checks=0;
  rv_hypervisor_stateen #(.HAS_SMSTATEEN(HAS_SMSTATEEN)) dut(.clk_i(clk),.rst_ni(rst_n),
    .csr_valid_i(valid),.csr_commit_write_i(write),.csr_address_i(address),.csr_write_data_i(data),
    .privilege_i(privilege),.virtual_i(virtual_mode),.csr_selected_o(selected),.csr_data_o(result),
    .csr_exception_o(exception),.csr_cause_o(cause),.envcfg_exception_o(env_exception),.envcfg_cause_o(env_cause));
  task automatic access(input logic [11:0] addr,input bit wr,input logic[63:0] value,
                        input logic[63:0] expected,input int trap=0);
    @(negedge clk);valid=1;write=wr;address=addr;data=value;#1;
    if(!selected || exception!==(trap!=0) || (trap!=0 && cause!==6'(trap)) || (!wr && trap==0 && result!==expected))
      $fatal(1,"stateen addr%h p%0d v%0d write%0d result%h exception%0d/%0d expected%h/%0d",addr,privilege,virtual_mode,wr,result,exception,cause,expected,trap);
    @(negedge clk);valid=0;write=0;checks++;
  endtask
  task automatic envcheck(input int trap);
    #1;if(env_exception!==(trap!=0) || (trap!=0 && env_cause!==6'(trap)))$fatal(1,"ENVCFG gate mismatch");checks++;
  endtask
  initial begin
    repeat(3)@(negedge clk);rst_n=1;
    if(HAS_SMSTATEEN)begin
      privilege=1;access(12'h60c,0,0,0,2);access(12'h10c,0,0,0,2);envcheck(2);
      privilege=3;
      for(int n=0;n<4;n++)access(12'(12'h30c+n),1,'1,0);
      for(int n=0;n<4;n++)access(12'(12'h30c+n),0,0,n==0?64'hc000000000000000:64'h8000000000000000);
    end else access(12'h30c,0,0,0,2);
    privilege=1;envcheck(0);
    for(int n=0;n<4;n++)begin
      access(12'(12'h60c+n),0,0,0);
      access(12'(12'h60c+n),1,'1,0);
      access(12'(12'h60c+n),0,0,n==0?64'hc000000000000000:64'h8000000000000000);
      access(12'(12'h10c+n),1,'1,0);access(12'(12'h10c+n),0,0,0);
    end
    virtual_mode=1;envcheck(0);
    for(int n=0;n<4;n++)access(12'(12'h10c+n),0,0,0);
    access(12'h60c,0,0,0,22);
    privilege=0;access(12'h60c,0,0,0,22);access(12'h10c,0,0,0,22);
    privilege=1;virtual_mode=0;
    access(12'h60c,1,0,0);virtual_mode=1;envcheck(22);access(12'h10c,0,0,0,22);
    virtual_mode=0;access(12'h60c,1,64'h8000000000000000,0);
    virtual_mode=1;envcheck(22);access(12'h10c,0,0,0);
    virtual_mode=0;access(12'h60c,1,64'h4000000000000000,0);
    virtual_mode=1;envcheck(0);access(12'h10c,0,0,0,22);
    privilege=3;virtual_mode=0;envcheck(0);
    if(HAS_SMSTATEEN)begin
      access(12'h30c,1,64'h8000000000000000,0);
      access(12'h60c,0,0,0);privilege=1;virtual_mode=1;envcheck(2);
      privilege=3;virtual_mode=0;access(12'h30c,1,64'h4000000000000000,0);
      privilege=1;virtual_mode=1;access(12'h10c,0,0,0,2);access(12'h60c,0,0,0,2);
    end
    $display("PASS rv_hypervisor_stateen_tb SM=%0d checks=%0d",HAS_SMSTATEEN,checks);$finish;
  end
endmodule

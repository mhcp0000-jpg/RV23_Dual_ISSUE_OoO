// RV64 Ssstateen view for the selected profile: no custom/JVT/Zfinx/AIA state.
// ENVCFG and each mandatory writable SE field are implemented. Optional
// Smstateen can provide the controlling machine bank; absent means enabled.
// Development component; architectural H remains disabled until integration.
module rv_hypervisor_stateen #(
  parameter bit HAS_SMSTATEEN=0
)(
  input logic clk_i,rst_ni,
  input logic csr_valid_i,csr_commit_write_i,
  input logic [11:0] csr_address_i,
  input logic [63:0] csr_write_data_i,
  input logic [1:0] privilege_i,
  input logic virtual_i,
  output logic csr_selected_o,
  output logic [63:0] csr_data_o,
  output logic csr_exception_o,
  output logic [5:0] csr_cause_o,
  output logic envcfg_exception_o,
  output logic [5:0] envcfg_cause_o
);
  logic [63:0] machine_q[4],hypervisor_q[4];
  logic [63:0] machine_value[4],hypervisor_value[4];
  logic machine_select,hypervisor_select,supervisor_select;
  logic [1:0] index;
  function automatic logic [63:0] implemented(input int n);
    return n==0?64'hc000000000000000:64'h8000000000000000;
  endfunction
  for(genvar n=0;n<4;n++)begin:g_mask
    assign machine_value[n]=HAS_SMSTATEEN?machine_q[n]:64'hffffffffffffffff;
    assign hypervisor_value[n]=hypervisor_q[n]&machine_value[n];
  end
  always_comb begin
    machine_select=csr_address_i[11:2]==10'h0c3;
    hypervisor_select=csr_address_i[11:2]==10'h183;
    supervisor_select=csr_address_i[11:2]==10'h043;
    index=csr_address_i[1:0];
    csr_selected_o=machine_select || hypervisor_select || supervisor_select;
    csr_data_o=machine_select?machine_value[index]:(hypervisor_select?hypervisor_value[index]:64'b0);
    csr_exception_o=0;csr_cause_o=2;
    if(csr_valid_i && csr_selected_o)begin
      if(machine_select)csr_exception_o=!HAS_SMSTATEEN || privilege_i!=3 || virtual_i;
      else if(privilege_i!=3 && !machine_value[index][63])csr_exception_o=1;
      else if(hypervisor_select)begin
        if(virtual_i)begin csr_exception_o=1;csr_cause_o=22;end
        else csr_exception_o=privilege_i==0;
      end else if(privilege_i==0)begin csr_exception_o=1;csr_cause_o=virtual_i?6'd22:6'd2;end
      else if(virtual_i && !hypervisor_value[index][63])begin csr_exception_o=1;csr_cause_o=22;end
    end
    envcfg_exception_o=0;envcfg_cause_o=2;
    if(privilege_i!=3)begin
      if(!machine_value[0][62])envcfg_exception_o=1;
      else if(virtual_i && !hypervisor_value[0][62])begin envcfg_exception_o=1;envcfg_cause_o=22;end
    end
  end
  always_ff @(posedge clk_i)begin
    if(!rst_ni)begin
      for(int n=0;n<4;n++)begin machine_q[n]<=0;hypervisor_q[n]<=0;end
    end else if(csr_valid_i && csr_commit_write_i && csr_selected_o && !csr_exception_o)begin
      if(machine_select && HAS_SMSTATEEN)machine_q[index]<=csr_write_data_i&implemented(int'(index));
      if(hypervisor_select)hypervisor_q[index]<=csr_write_data_i&implemented(int'(index))&machine_value[index];
      // No sstateen-controlled optional state is present; all bits are RAZ.
    end
  end
endmodule

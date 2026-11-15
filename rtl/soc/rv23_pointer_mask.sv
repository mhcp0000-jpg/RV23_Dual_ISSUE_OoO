// Explicit data-address transformation only. Fetch/PTE addresses and CSR
// software writes must never pass through this unit. Ssnpm configures U-mode;
// effective privilege (including MPRV) and effective MXR govern the operation.
module rv23_pointer_mask #(
  parameter bit ENABLE=1
)(
  input logic [63:0] address_i,
  input logic [1:0] privilege_i,pmm_i,
  input logic translated_i,mxr_i,
  output logic [63:0] address_o
);
  always_comb begin
    address_o=address_i;
    if(ENABLE && privilege_i==0 && !mxr_i && pmm_i==2)
      address_o={{7{translated_i && address_i[56]}},address_i[56:0]};
  end
endmodule

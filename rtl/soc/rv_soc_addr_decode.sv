module rv_soc_addr_decode #(
  parameter logic [31:0] BOOTROM_BASE_ADDR = rv_soc_pkg::BOOTROM_BASE_ADDR,
  parameter int unsigned BOOTROM_SIZE_KB   = rv_soc_pkg::BOOTROM_SIZE_KB,
  parameter logic [31:0] CLINT_BASE_ADDR   = rv_soc_pkg::CLINT_BASE_ADDR,
  parameter int unsigned CLINT_SIZE_KB     = rv_soc_pkg::CLINT_SIZE_KB,
  parameter logic [31:0] PLIC_BASE_ADDR    = rv_soc_pkg::PLIC_BASE_ADDR,
  parameter int unsigned PLIC_SIZE_KB      = rv_soc_pkg::PLIC_SIZE_KB,
  parameter logic [31:0] HOSTIF_BASE_ADDR  = rv_soc_pkg::HOSTIF_BASE_ADDR,
  parameter int unsigned HOSTIF_SIZE_KB    = rv_soc_pkg::HOSTIF_SIZE_KB,
  parameter logic [31:0] ITIM_BASE_ADDR    = rv_soc_pkg::ITIM_BASE_ADDR,
  parameter int unsigned ITIM_SIZE_KB      = rv_soc_pkg::ITIM_SIZE_KB,
  parameter logic [31:0] DTIM_BASE_ADDR    = rv_soc_pkg::DTIM_BASE_ADDR,
  parameter int unsigned DTIM_SIZE_KB      = rv_soc_pkg::DTIM_SIZE_KB
) (
  input  logic [31:0]                addr_i,
  output rv_soc_pkg::soc_target_e    target_o
);

  import rv_soc_pkg::*;


  assign target_o = rv23_pkg::decode_target(addr_i);
endmodule

package rv23_pkg;
  parameter logic [31:0] SRAM_BASE = 32'h8000_0000;
  parameter int unsigned SRAM_KB = 1024;
  parameter int unsigned ICACHE_KB = 32;
  parameter int unsigned DCACHE_KB = 32;
  parameter int unsigned CACHE_LINE_BYTES = 64;
  // One address map for both AXI burst validation and the standalone decoder.
  function automatic rv_soc_pkg::soc_target_e decode_target(input logic [31:0] addr);
    import rv_soc_pkg::*;
    if (addr_in_region(addr, SRAM_BASE, size_kb_to_bytes(SRAM_KB)))
      return SOC_TARGET_I_LOCAL;
    if (addr_in_region(addr, CLINT_BASE_ADDR, size_kb_to_bytes(CLINT_SIZE_KB)))
      return SOC_TARGET_D_LOCAL;
    if (addr_in_region(addr, PLIC_BASE_ADDR, size_kb_to_bytes(PLIC_SIZE_KB)))
      return SOC_TARGET_PLIC;
    if (addr_in_region(addr, HOSTIF_BASE_ADDR, size_kb_to_bytes(HOSTIF_SIZE_KB)))
      return SOC_TARGET_HOSTIF;
    if (addr_in_region(addr, BOOTROM_BASE_ADDR, size_kb_to_bytes(BOOTROM_SIZE_KB)))
      return SOC_TARGET_RESERVED;
    return SOC_TARGET_ERROR;
  endfunction
endpackage

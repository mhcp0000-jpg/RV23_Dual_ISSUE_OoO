OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY
{
  CODE (rwx) : ORIGIN = 0x80000000, LENGTH = 128K
  DATA (rwx) : ORIGIN = 0x80020000, LENGTH = 896K
}
SECTIONS
{
  .text : { KEEP(*(.text.init)) *(.text .text.*) *(.rodata .rodata.*) } > CODE
  .tohost : { KEEP(*(.tohost)) } > DATA
  .data : ALIGN(4096) { *(.sdata .sdata.*) *(.data .data.*) } > DATA
  .bss (NOLOAD) : ALIGN(16) { *(.sbss .sbss.*) *(.bss .bss.*) *(COMMON) } > DATA
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.riscv.attributes) }
}

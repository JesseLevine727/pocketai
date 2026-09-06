OUTPUT_ARCH("riscv")
ENTRY(_reset_entry)
MEMORY { ram (rwx) : ORIGIN = 0, LENGTH = 0x10000 }
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); results PT_LOAD FLAGS(6); }
_stack_top = 0x10000;
SECTIONS {
  .vectors 0 : { KEEP(*(.vectors)) } > ram :text
  .text : { *(.text .text.*) } > ram :text
  .rodata : { *(.rodata .rodata.* .srodata .srodata.*) } > ram :text
  .data : { *(.data .data.* .sdata .sdata.*) } > ram :data
  .bss (NOLOAD) : {
    . = ALIGN(4); *(.bss .bss.* .sbss .sbss.* COMMON)
    _bss_end = .;
  } > ram :data
  .results 0xd000 : { KEEP(*(.results)) } > ram :results
  ASSERT(_bss_end <= 0xc000, "memory-test code/data overlaps reserved region")
  ASSERT(SIZEOF(.results) == 128, "memory-test result ABI mismatch")
}
_reset_entry = 0x80;

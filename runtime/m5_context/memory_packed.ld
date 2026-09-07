OUTPUT_ARCH("riscv")
ENTRY(_reset_entry)
MEMORY { ram (rwx) : ORIGIN = 0, LENGTH = 0x10000 }
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); scores PT_LOAD FLAGS(6); results PT_LOAD FLAGS(6); lookup PT_LOAD FLAGS(6); constants PT_LOAD FLAGS(4); }
_stack_top = 0x10000;
SECTIONS {
  .vectors 0 : { KEEP(*(.vectors)) } > ram :text
  .text : { *(.text .text.*) } > ram :text
  .data : { *(.data .data.* .sdata .sdata.*) } > ram :data
  .bss (NOLOAD) : {
    . = ALIGN(4); *(.bss .bss.* .sbss .sbss.* COMMON)
    _bss_end = .;
  } > ram :data
  .context_scores 0xc000 (NOLOAD) : { *(.context_scores) } > ram :scores
  .results 0xd000 : { KEEP(*(.results)) } > ram :results
  .context_lookup 0xd080 (NOLOAD) : { *(.context_lookup) } > ram :lookup
  /* Model-independent literals occupy the remaining reserved gap. No code,
   * result ABI, local-score storage, lookup data or hart stack may overlap. */
  .rodata 0xd880 : { *(.rodata .rodata.* .srodata .srodata.*) *(.eh_frame .eh_frame.*) } > ram :constants
  ASSERT(_bss_end <= 0xc000, "code/data overlaps local scores")
  ASSERT(SIZEOF(.context_scores) == 4096, "local score capacity")
  ASSERT(SIZEOF(.results) == 128, "unchanged result ABI")
  ASSERT(SIZEOF(.context_lookup) == 2048, "exact lookup capacity")
  ASSERT(ADDR(.rodata)+SIZEOF(.rodata) <= 0xe000, "constants overlap hart1 stack")
}
_reset_entry = 0x80;

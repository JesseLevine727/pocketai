/* PocketAI-T M1b cluster test: linker script.
 * RAM @ 0x0000_0000, 64 KB (shared by both harts). One image for both
 * harts; per-hart stacks are carved out from the top (0x800 per hart in
 * crt0.S). Reset vector slot is at vector-base + 0x80.
 */
OUTPUT_ARCH("riscv")
ENTRY(_entry_point)

MEMORY {
  ram (rwx) : ORIGIN = 0x00000000, LENGTH = 0x10000
}

PHDRS {
  text    PT_LOAD FLAGS(5); /* read + execute */
  data    PT_LOAD FLAGS(6); /* read + write */
  results PT_LOAD FLAGS(6); /* AXI-visible initialized result ABI */
}

_stack_len   = 0x1000;
_stack_top   = ORIGIN(ram) + LENGTH(ram);

SECTIONS
{
  .vectors : {
    . = ALIGN(4);
    _vectors_start = .;
    KEEP(*(.vectors))
  } > ram :text

  .text : {
    . = ALIGN(4);
    *(.text)
    *(.text.*)
  } > ram :text

  .rodata : {
    . = ALIGN(4);
    *(.srodata)
    *(.srodata.*)
    *(.rodata)
    *(.rodata.*)
  } > ram :text

  .data : {
    . = ALIGN(4);
    *(.sdata)
    *(.sdata.*)
    *(.data)
    *(.data.*)
  } > ram :data

  .bss (NOLOAD) : {
    . = ALIGN(4);
    _bss_start = .;
    *(.sbss)
    *(.sbss.*)
    *(.bss)
    *(.bss.*)
    *(COMMON)
    _bss_end = .;
  } > ram :data

  .results 0x0000d000 : {
    . = ALIGN(4);
    _results_start = .;
    KEEP(*(.results))
    _results_end = .;
  } > ram :results

  ASSERT(_results_start == 0x0000d000,
         "M1 result ABI moved from 0x0000d000")
  ASSERT((_results_end - _results_start) == 0x34,
         "M1 result ABI size changed")
  ASSERT(_bss_end <= 0x0000c000,
         "firmware overlaps AXI self-test scratch area")
}

_entry_point = _vectors_start + 0x80;

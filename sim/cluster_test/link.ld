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

_min_stack   = 0x800;
_stack_len   = 0x1000;
_stack_start = ORIGIN(ram) + LENGTH(ram) - _min_stack;

SECTIONS
{
  .vectors : {
    . = ALIGN(4);
    _vectors_start = .;
    KEEP(*(.vectors))
  } > ram

  .text : {
    . = ALIGN(4);
    *(.text)
    *(.text.*)
  } > ram

  .rodata : {
    . = ALIGN(4);
    *(.srodata)
    *(.srodata.*)
    *(.rodata)
    *(.rodata.*)
  } > ram

  .data : {
    . = ALIGN(4);
    *(.sdata)
    *(.sdata.*)
    *(.data)
    *(.data.*)
  } > ram

  .bss (NOLOAD) : {
    . = ALIGN(4);
    _bss_start = .;
    *(.sbss)
    *(.sbss.*)
    *(.bss)
    *(.bss.*)
    *(COMMON)
    _bss_end = .;
  } > ram
}

_entry_point = _vectors_start + 0x80;

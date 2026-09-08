OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {
  . = 0;
  .vectors : { *(.vectors) }
  .text : { *(.text*) }
  /DISCARD/ : { *(.comment) *(.riscv.attributes) }
}

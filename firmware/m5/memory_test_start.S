/* The loader writes/verifies the complete zero-padded RAM image under reset.
 * Neither hart races the other by clearing shared BSS after release. */
.section .vectors, "ax"
.option norvc
.global _start
_start:
.rept 32
  jal x0, m5_memory_trap
.endr
.org 0x80
  jal x0, reset_handler
.section .text
reset_handler:
  csrr a0, mhartid
  slli t0, a0, 12
  la sp, _stack_top
  sub sp, sp, t0
  li t0, 1
  csrw mtvec, t0
  csrw mie, zero
  call m5_memory_main
1:
  wfi
  j 1b

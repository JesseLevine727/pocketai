/* Minimal repro: does csrr mhartid work? */
  .section .vectors, "ax"
  .option norvc
  .org 0x0
  .rept 32
  jal x0, default
  .endr
  .org 0x80
  jal x0, run
  .section .text
run:
  csrr a0, 0xf14        /* mhartid: 0 -> 'A', 1 -> 'B' */
  addi a0, a0, 0x41
  li   a1, 0x11000
  sw   a0, 0(a1)
  li   a2, 1
  sw   a2, 8(a1)        /* halt */
  wfi
default:
  wfi

// SPI loads this image into actual SRAM. Both harts execute their fast MUL,
// return separate answers in scratchpad, and print their IDs through the UART.
.section .vectors, "ax"
.option norvc
.global _start
.org 0x80
_start:
  csrw mie, zero
  csrr a0, mhartid
  li a1, 123
  add a1, a1, a0
  li a2, 45
  mul a3, a1, a2
  li t0, 0x1000
  slli t1, a0, 2
  add t0, t0, t1
  sw a3, 0(t0)
  li t0, 0x11000
  addi a0, a0, 48
  sw a0, 0(t0)
1: wfi
  j 1b

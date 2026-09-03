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
  csrr t0, 0xf11     /* mvendorid */
  li   t1, 0x41
  sw   t1, 0(t0)     /* trap -> default -> wfi (silent); no write = OK */
  csrr t0, 0x300     /* mstatus */
  li   t1, 0x42
  sw   t1, 0(t0)
  csrr t0, 0xf14     /* mhartid */
  li   t1, 0x43
  sw   t1, 0(t0)
  li   t1, 0x4a      /* 'J' = all three reads OK */
  li   t2, 0x11000
  sw   t1, 0(t2)
  li   a2, 1
  sw   a2, 8(t0)
  wfi
default:
  wfi

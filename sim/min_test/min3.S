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
  csrr t0, 0x300     /* mstatus: legal even in U mode */
  li   t2, 0x11000
  li   t1, 0x30       /* '0' */
  sw   t1, 0(t2)
  csrr t0, 0xf11     /* mvendorid: needs M */
  li   t1, 0x31       /* '1' */
  sw   t1, 0(t2)
  li   t1, 0x4a       /* 'J' done */
  sw   t1, 0(t2)
  li   a3, 1
  sw   a3, 8(t2)
  wfi
default:
  wfi

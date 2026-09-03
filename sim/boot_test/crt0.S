/* PocketAI-T M1a boot smoke: startup code.
 *
 * The CPU resets with its PC at boot_addr + 0x80 (the "reset vector" slot of
 * the mtvec table). We place a jump to `reset_handler` at that offset. After
 * running C main() we put the core to sleep (the real halt is done by main()
 * writing to the UART ctrl register).
 */

  .section .vectors, "ax"
  .option norvc;

  .org 0x00
  .rept 32
  jal x0, default_exc_handler
  .endr

  /* Reset vector (boot_addr + 0x80) */
  .org 0x80
  jal x0, reset_handler

  .section .text

reset_handler:
  /* Clear GPRs (keep sp). */
  mv  x1, x0
  mv  x2, x1
  mv  x3, x1
  mv  x4, x1
  mv  x5, x1
  mv  x6, x1
  mv  x7, x1
  mv  x8, x1
  mv  x9, x1
  mv x10, x1
  mv x11, x1
  mv x12, x1
  mv x13, x1
  mv x14, x1
  mv x15, x1
  mv x16, x1
  mv x17, x1
  mv x18, x1
  mv x19, x1
  mv x20, x1
  mv x21, x1
  mv x22, x1
  mv x23, x1
  mv x24, x1
  mv x25, x1
  mv x26, x1
  mv x27, x1
  mv x28, x1
  mv x29, x1
  mv x30, x1
  mv x31, x1

  /* Stack pointer */
  la  x2, _stack_start

  /* Point trap vector at the (safe) default handler */
  la  x3, default_exc_handler
  csrw mtvec, x3

  /* Clear BSS */
  la x26, _bss_start
  la x27, _bss_end
bss_loop:
  bge x26, x27, bss_done
  sw x0, 0(x26)
  addi x26, x26, 4
  j  bss_loop
bss_done:

  /* Call main() */
  call main

  /* main() returned; put the core to sleep (should not happen). */
sleep_loop:
  wfi
  j  sleep_loop

default_exc_handler:
  wfi
  j  default_exc_handler

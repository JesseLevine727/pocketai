/* PocketAI-T M1b cluster test: startup code.
 *
 * The CPU resets with its PC at boot_addr + 0x80 (the "reset vector" slot of
 * the mtvec table). We place a jump to `reset_handler` at that offset. Both
 * harts run the same image; the per-hart behaviour (including a separate
 * stack) is selected from mhartid.
 */

  .section .vectors, "ax"
  .option norvc;

  /* Ibex implements mtvec in vectored mode with a 256-byte-aligned base.
   * Entry N is therefore base + 4*N for interrupt cause N, while synchronous
   * exceptions enter at base. Machine external interrupt is cause 11. */
  .org 0x00
  .rept 11
  jal x0, default_exc_handler
  .endr
  jal x0, machine_trap_handler
  .rept 20
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

  /* Per-hart stack pointer: sp = _stack_top - (mhartid + 1) * 0x800.
   * Both harts share one RAM image and (read-only) vectors, so the stacks
   * must not overlap. Hart 0 starts at 0xf800; hart 1 starts at 0xf000. */
  csrr x5, 0xf14            /* mhartid */
  addi x5, x5, 1
  slli x5, x5, 11           /* (mhartid + 1) * 0x800 */
  la   x2, _stack_top
  sub  x2, x2, x5

  /* GCC's machine-interrupt handler saves/restores the registers it uses and
   * returns with mret. Ibex forces vectored mode, so install the aligned table
   * base rather than the C handler address. */
  la  x3, _vectors_start
  ori x3, x3, 1
  csrw mtvec, x3

  /* Keep interrupts disabled until both harts have completed bootstrap. */
  csrw mie, x0

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

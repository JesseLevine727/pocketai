/* PocketAI-T M1b cluster test: main program.
 *
 * One ELF image for both harts; main() branches on mhartid.
 *
 *   hart 1: print "H1 BOOT", write 0x52454144 to mbox@0x12004 (1 -> 0),
 *           wait until status bit0 (pend0), read mbox@0x12000;
 *           "P1: PONG OK" if 0x50494E47, else "P1: FAIL", halt.
 *   hart 0: print "P0", write 0x50494E47 to mbox@0x12000 (0 -> 1),
 *           wait until status bit1 (pend1), write 0xC0DEF000 to RAM@0x1000,
 *           halt.
 *
 * Waiting is a tight poll on the mailbox status register (levels: a status
 * read neither clears nor affects the pending bits).  The external IRQ lines
 * from the mailbox are wired to the cores, but mstatus.MIE / mie.MEIE are
 * left at 0, so they are wired-but-unused by this test (a pending external
 * interrupt is simply never taken).
 */
#include <stdint.h>

#define UART_OUT    0x11000u /* write lower byte -> captured               */
#define UART_CTRL   0x11008u /* write 1 -> halt the simulator              */
#define MBOX_0_TO_1 0x12000u /* 0 -> 1 word                                */
#define MBOX_1_TO_0 0x12004u /* 1 -> 0 word                                */
#define MBOX_STATUS 0x12008u /* bit0 = pend0 (0 wrote), bit1 = pend1 (1 wr) */
#define RAM_TEST    0x1000u  /* scratch word, unused by the image          */

static inline void wr32(uint32_t addr, uint32_t val) {
  *(volatile uint32_t *)addr = val;
}

static inline uint32_t rd32(uint32_t addr) {
  return *(volatile uint32_t *)addr;
}

static inline uint32_t mhartid(void) {
  uint32_t id;
  __asm__ volatile("csrr %0, 0xf14" : "=r"(id));
  return id;
}

static void uart_putc(uint32_t c) {
  wr32(UART_OUT, c);
}

static void uart_puts(const char *s) {
  while (*s) {
    uart_putc((uint32_t)*s++);
  }
}

void main(void) {
  if (mhartid() == 1) {
    uart_puts("H1 BOOT\n");
    wr32(MBOX_1_TO_0, 0x52454144);
    while (!(rd32(MBOX_STATUS) & 0x1)) {
    } /* wait for pend0 (bit0): hart 0 wrote 0 -> 1 */
    uint32_t v = rd32(MBOX_0_TO_1);
    if (v == 0x50494E47) {
      uart_puts("P1: PONG OK\n");
    } else {
      uart_puts("P1: FAIL\n");
    }
  } else {
    uart_puts("P0\n");
    wr32(MBOX_0_TO_1, 0x50494E47);
    while (!(rd32(MBOX_STATUS) & 0x2)) {
    } /* wait for pend1 (bit1): hart 1 wrote 1 -> 0 */
    wr32(RAM_TEST, 0xC0DEF000);
  }
  if (mhartid() == 1) {
    wr32(UART_CTRL, 1); /* hart 1 halts last so its output is not lost */
  }

  for (;;) {
    __asm__ volatile("wfi");
  }
}

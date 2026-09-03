/* PocketAI-T M1a boot smoke: main program.
 *
 * Prints "PA M1 BOOT" over the UART byte-capture register (at 0x0001_1000),
 * then halts the simulation by writing to the ctrl register (offset +8).
 */
#include <stdint.h>

#define UART_BASE   0x11000u
#define UART_OUT    (UART_BASE + 0x0) /* write lower byte -> captured   */
#define UART_CTRL   (UART_BASE + 0x8) /* write 1 -> halt the simulator  */

#define DEV_WRITE(addr, val) (*((volatile uint32_t *)(addr)) = (uint32_t)(val))

static void uart_putc(uint32_t c) {
  DEV_WRITE(UART_OUT, c);
}

static void uart_puts(const char *s) {
  while (*s) {
    uart_putc((uint32_t)*s++);
  }
}

void main(void) {
  uart_puts("PA M1 BOOT\n");
  DEV_WRITE(UART_CTRL, 1); /* halt */

  for (;;) {
    __asm__ volatile("wfi");
  }
}

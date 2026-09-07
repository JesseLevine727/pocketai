/* Directed no-trap WFI tests on both actual fast Ibex harts, followed by the
 * unchanged memory/trap/reset regression. Shared fields are zeroed by loader. */
#define m5_memory_main m5_original_memory_main
#include "../m5/memory_test.c"
#undef m5_memory_main
#include "../../runtime/m5_iterate/mailbox_wait.c.inc"
#define MBOX(off) (*(volatile uint32_t *)(0x12000u + (off)))
#define SFPU(off) (*(volatile uint32_t *)(0x14000u + (off)))
static volatile uint32_t phase[2];

static void delay(uint32_t n) {
  uint32_t start = cycles();
  while ((uint32_t)(cycles() - start) < n) __asm__ volatile("nop");
}
static void no_traps(uint32_t hart) {
  uint32_t status, enable;
  __asm__ volatile("csrr %0, mstatus\ncsrr %1, mie" : "=r"(status), "=r"(enable));
  check(hart, !(status & 8u) && (enable & 2048u) && !result[hart].traps, 0x10000);
}

void m5_memory_main(uint32_t hart) {
  MBOX(12) = hart ? 1 : 2;
  phase[hart] = 1;
  while (!phase[1-hart]) { }
  if (hart == 1) {
    /* Pending first with local interrupts disabled, then enabled before WFI.
     * Two WFIs without acknowledgement prove the event is sticky. */
    phase[1] = 2;
    while (phase[0] != 2) { }
    uint32_t enable, pending;
    __asm__ volatile("csrr %0, mie\ncsrr %1, mip" : "=r"(enable), "=r"(pending));
    check(hart, !(enable & 2048u) && (pending & 2048u) && MBOX(0) == 0x1111, 0x20000);
    pa_iter_enable_mailbox_wait();
    __asm__ volatile("wfi\nwfi" ::: "memory");
    check(hart, (MBOX(8) & 1u) && (MBOX(8) & 1u), 0x40000);
    MBOX(12) = 1;
    check(hart, !(MBOX(8) & 1u), 0x80000);
    phase[1] = 3;
    /* An unrelated enabled SFPU error wakes WFI but is not a message. */
    __asm__ volatile("wfi" ::: "memory");
    check(hart, !(MBOX(8) & 1u) && (SFPU(4) & 8u), 0x100000);
    phase[1] = 4;
    pa_iter_wait_mailbox(1);
    check(hart, MBOX(0) == 0x2222, 0x200000);
    MBOX(12) = 1;
    phase[1] = 5;
    for (uint32_t i = 1; i <= 64; ++i) {
      pa_iter_wait_mailbox(1);
      check(hart, MBOX(0) == i, 0x400000);
      MBOX(12) = 1;
      no_traps(hart);
      MBOX(4) = i;
    }
    phase[1] = 6;
    while (phase[0] != 6) { }
  } else {
    while (phase[1] != 2) { }
    MBOX(0) = 0x1111;
    phase[0] = 2;
    while (phase[1] != 3) { }
    delay(1000);
    SFPU(8) = 0; SFPU(12) = 0; SFPU(0x40) = 1; SFPU(28) = 1;
    while (phase[1] != 4) { }
    delay(1000);
    check(hart, phase[1] == 4, 0x800000);
    SFPU(0x40) = 0; SFPU(28) = 2;
    delay(1000);
    MBOX(0) = 0x2222;
    while (phase[1] != 5) { }
    pa_iter_enable_mailbox_wait();
    for (uint32_t i = 1; i <= 64; ++i) {
      delay(i * 7);
      MBOX(0) = i;
      if (i & 1u) {
        while (!(MBOX(8) & 2u)) { }
        __asm__ volatile("wfi\nwfi" ::: "memory");
      }
      pa_iter_wait_mailbox(2);
      check(hart, MBOX(4) == i, 0x1000000);
      MBOX(12) = 2;
      check(hart, !(MBOX(8) & 2u), 0x2000000);
      no_traps(hart);
    }
    while (phase[1] != 6) { }
    phase[0] = 6;
  }
  __asm__ volatile("csrw mie, zero" ::: "memory");
  result[hart].reserved[0] = 64;
  m5_original_memory_main(hart);
}

/* Regression seam: the model and service timer is hart 0 mcycle. Hart 1
 * deliberately stays active for >=20,000 clocks before replying. The elapsed
 * model counter MUST include that wait. ITER_POLL=0 reproduces WFI undercount. */
#define m5_memory_main m5_original_memory_main
#include "../m5/memory_test.c"
#undef m5_memory_main
#include "../../runtime/m5_iterate/mailbox_wait.c.inc"
static volatile uint32_t clock_phase;
void m5_memory_main(uint32_t hart) {
  if (!hart) {
    pa_iter_enable_mailbox_wait();
    uint32_t start = cycles();
    clock_phase = 1;
#if ITER_POLL
    while (!(*(volatile uint32_t *)0x12008u & 2u)) __asm__ volatile("nop");
#endif
    pa_iter_wait_mailbox(2);
    uint32_t elapsed = cycles() - start;
    check(hart, elapsed >= 20000, 0x10000);
    *(volatile uint32_t *)0x1200cu = 2;
    clock_phase = 2;
    __asm__ volatile("csrw mie, zero" ::: "memory");
  } else {
    while (clock_phase != 1) { }
    uint32_t start = cycles();
    while ((uint32_t)(cycles()-start) < 20000) __asm__ volatile("nop");
    *(volatile uint32_t *)0x12004u = 1;
    while (clock_phase != 2) { }
  }
  m5_original_memory_main(hart);
}

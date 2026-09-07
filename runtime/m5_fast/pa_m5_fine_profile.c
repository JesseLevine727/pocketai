#include "pa_m5_fine_profile.h"
uint32_t pa_fast_profile_enabled, pa_fast_profile_head;
static uint64_t elapsed[PA_FAST_PROFILE_COUNT];
static uint32_t calls[PA_FAST_PROFILE_COUNT];
uint64_t pa_fast_profile_begin(void) {
  if (!pa_fast_profile_enabled) return 0;
#ifdef __riscv
  uint32_t high0, low, high1;
  do {
    __asm__ volatile("csrr %0, mcycleh" : "=r"(high0));
    __asm__ volatile("csrr %0, mcycle" : "=r"(low));
    __asm__ volatile("csrr %0, mcycleh" : "=r"(high1));
  } while (high0 != high1);
  return ((uint64_t)high0 << 32) | low;
#else
  return 0;
#endif
}
void pa_fast_profile_end(uint32_t kind, uint64_t start) {
  if (!pa_fast_profile_enabled || kind >= PA_FAST_PROFILE_COUNT) return;
  elapsed[kind] += pa_fast_profile_begin() - start;
  ++calls[kind];
}
void pa_fast_profile_publish(volatile uint32_t *destination) {
  destination[0] = UINT32_C(0x314e4946); destination[1] = 1;
  destination[2] = PA_FAST_PROFILE_COUNT; destination[3] = pa_fast_profile_enabled;
  for (uint32_t i = 0; i < PA_FAST_PROFILE_COUNT; ++i) {
    destination[4+i*4] = i; destination[5+i*4] = calls[i];
    destination[6+i*4] = (uint32_t)elapsed[i];
    destination[7+i*4] = (uint32_t)(elapsed[i] >> 32);
  }
}

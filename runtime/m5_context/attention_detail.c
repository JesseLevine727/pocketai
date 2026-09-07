#include "attention_detail.h"
static uint64_t elapsed[CTX_COUNT];
static uint32_t count[CTX_COUNT];
uint64_t pa_context_begin(void) {
  uint32_t high0, low, high1;
  do {
    __asm__ volatile("csrr %0, mcycleh" : "=r"(high0));
    __asm__ volatile("csrr %0, mcycle" : "=r"(low));
    __asm__ volatile("csrr %0, mcycleh" : "=r"(high1));
  } while (high0 != high1);
  return ((uint64_t)high0 << 32) | low;
}
void pa_context_end(uint32_t kind, uint64_t start) {
  elapsed[kind] += pa_context_begin()-start;
  ++count[kind];
}
void pa_context_publish(volatile uint32_t *output) {
  output[0] = UINT32_C(0x36585443); output[1] = 1; output[2] = CTX_COUNT;
  for (uint32_t i = 0; i < CTX_COUNT; ++i) {
    output[3+i*3] = count[i];
    output[4+i*3] = (uint32_t)elapsed[i];
    output[5+i*3] = (uint32_t)(elapsed[i] >> 32);
  }
}

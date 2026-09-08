/* Bounded cache experiment: identical numerical work, independently per hart.
 * This is a local-memory/soft-binary64 microbenchmark, not GPT-2 throughput. */
#include "pa_m5_numerics.h"
#include <stdint.h>
#ifdef STARTUP_PROBE_HOST
#include <stdio.h>
#endif
struct probe_result {
  uint32_t state, errors, hash, cache, begin, end, instructions, cause;
  uint32_t address, pc, reserved[6];
};
#ifndef STARTUP_PROBE_HOST
static volatile struct probe_result results[2]
    __attribute__((section(".results"))) = {{0}, {0}};
#define REG(base, off) (*(volatile uint32_t *)((base) + (off)))
#endif
static uint32_t fnv(uint32_t hash, uint32_t value) {
  return (hash ^ value) * UINT32_C(16777619);
}
static uint32_t probe(uint32_t hart) {
  int16_t values[16], gains[16];
  int32_t biases[16];
  double gain[16], bias[16], scales[16];
  uint32_t multipliers[16], factor, shift;
  uint32_t hash = UINT32_C(2166136261), value = 123456789u + hart;
  for (uint32_t repeat = 0; repeat < 4; ++repeat) {
    for (uint32_t i = 0; i < 16; ++i) {
      value = value * UINT32_C(1664525) + UINT32_C(1013904223);
      values[i] = (int16_t)(value >> 16);
      gain[i] = (double)((int32_t)(value & 2047u) - 1024) / 128.0;
      bias[i] = (double)((int32_t)((value >> 11) & 1023u) - 512) / 64.0;
      scales[i] = (double)((value & 8191u) + 1) / 4096.0;
    }
    hash = fnv(hash, (uint32_t)pa_m5_layernorm_metadata(
        values, 16, hart + repeat, gain, bias, gains, biases, &factor));
    hash = fnv(hash, factor);
    hash = fnv(hash, (uint32_t)pa_m5_affine_metadata(scales, 16, multipliers, &shift));
    hash = fnv(hash, shift);
    for (uint32_t i = 0; i < 16; ++i) {
      hash = fnv(hash, (uint16_t)gains[i]);
      hash = fnv(hash, (uint32_t)biases[i]);
      hash = fnv(hash, multipliers[i]);
      hash = fnv(hash, pa_m5_dynamic_multiplier((uint16_t)values[i] >> 1));
      hash = fnv(hash, (uint32_t)pa_m5_rne_f64_signed(bias[i] / 2.0));
      uint64_t product = (uint64_t)value * (hash | 1u);
      hash = fnv(hash, (uint32_t)(product >> 32));
    }
  }
  return hash;
}
#ifdef STARTUP_PROBE_HOST
int main(void) {
  printf("[%u,%u]\n", probe(0), probe(1));
  return 0;
}
#else
void m5_memory_trap(void) __attribute__((interrupt("machine")));
void m5_memory_trap(void) {
  uint32_t hart, value;
  __asm__ volatile("csrr %0, mhartid" : "=r"(hart));
  __asm__ volatile("csrr %0, mcause" : "=r"(value)); results[hart].cause = value;
  __asm__ volatile("csrr %0, mtval" : "=r"(value)); results[hart].address = value;
  __asm__ volatile("csrr %0, mepc" : "=r"(value)); results[hart].pc = value;
  results[hart].errors = 1; REG(0x11000u, 8) = 1;
  for (;;) __asm__ volatile("wfi");
}
void m5_memory_main(uint32_t hart) {
  uint32_t start, end, instructions, current;
  __asm__ volatile("csrr %0, 0x7c0" : "=r"(current));
  results[hart].cache = current & 1;
  if ((current & 1) != STARTUP_ICACHE_ENABLE) results[hart].errors = 2;
  results[hart].state = 1;
  __asm__ volatile("csrr %0, mcycle" : "=r"(start));
  __asm__ volatile("csrr %0, minstret" : "=r"(instructions));
  results[hart].hash = probe(hart);
  __asm__ volatile("csrr %0, minstret" : "=r"(current));
  __asm__ volatile("csrr %0, mcycle" : "=r"(end));
  results[hart].begin = start; results[hart].end = end;
  results[hart].instructions = current - instructions;
  __asm__ volatile("fence rw, rw" ::: "memory"); results[hart].state = 2;
  if (!hart) {
    while (results[1].state != 2) __asm__ volatile("nop");
    results[0].state = 3; REG(0x11000u, 8) = 1;
  }
  for (;;) __asm__ volatile("wfi");
}
#endif

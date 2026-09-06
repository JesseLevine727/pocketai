/* Bounded single-hart probes: SRAM vs scalar DDR and exact metadata arithmetic. */
#include "pa_m5_numerics.h"
#define REG(base, off) (*(volatile uint32_t *)((base) + (off)))
#define WORK UINT32_C(0x4f1f9000)
#define TRACE UINT32_C(0x4f5fa000)
static volatile uint32_t results[32] __attribute__((section(".results"))) = {0};
static volatile uint32_t local_words[512];
static double local_scales[512];
static uint32_t local_multipliers[512];
extern uint64_t pa_m5_baseline_rne_u64(uint64_t, uint64_t);
extern int pa_m5_baseline_affine_metadata(const double *, uint32_t, uint32_t *, uint32_t *);
static uint64_t cycles(void) {
  uint32_t a, b, c;
  do {
    __asm__ volatile("csrr %0,mcycleh" : "=r"(a));
    __asm__ volatile("csrr %0,mcycle" : "=r"(b));
    __asm__ volatile("csrr %0,mcycleh" : "=r"(c));
  } while (a != c);
  return (uint64_t)a << 32 | b;
}
static void publish(unsigned id, uint64_t elapsed, uint64_t checksum, uint32_t operations) {
  volatile uint32_t *record = (volatile uint32_t *)TRACE + 8 + id * 6;
  record[0] = id; record[1] = (uint32_t)elapsed; record[2] = (uint32_t)(elapsed >> 32);
  record[3] = (uint32_t)checksum; record[4] = (uint32_t)(checksum >> 32); record[5] = operations;
}
void m5_memory_trap(void) __attribute__((interrupt("machine")));
void m5_memory_trap(void) {
  results[0] = 5;
  __asm__ volatile("csrr %0,mcause" : "=r"(results[1]));
  __asm__ volatile("csrr %0,mtval" : "=r"(results[2]));
  __asm__ volatile("csrr %0,mepc" : "=r"(results[3]));
  __asm__ volatile("fence rw,rw" ::: "memory"); REG(0x11000, 8) = 1;
  for (;;) __asm__ volatile("wfi");
}
void m5_memory_main(uint32_t hart) {
  if (hart) for (;;) __asm__ volatile("wfi");
  volatile uint32_t *ddr_words = (volatile uint32_t *)(WORK + 0x3000);
  double *ddr_scales = (double *)(WORK + 0x4000);
  uint32_t *ddr_multipliers = (uint32_t *)(WORK + 0x6000);
  for (unsigned i = 0; i < 512; ++i) {
    local_words[i] = ddr_words[i] = i + 1;
    local_scales[i] = ddr_scales[i] = (double)(i + 1) / 64.;
  }
  for (unsigned id = 0; id < 2; ++id) {
    volatile uint32_t *source = id ? ddr_words : local_words;
    uint64_t start = cycles(); uint32_t sum = 0;
    for (unsigned repeat = 0; repeat < 64; ++repeat)
      for (unsigned i = 0; i < 512; ++i) sum += source[i];
    publish(id, cycles() - start, sum, 32768);
  }
  for (unsigned id = 2; id < 4; ++id) {
    uint64_t start = cycles(), sum = 0;
    for (unsigned i = 0; i < 8192; ++i) {
      uint64_t numerator = ((uint64_t)i << 26) + (i & 1 ? (1u << 23) : 1u);
      sum += id == 2 ? pa_m5_baseline_rne_u64(numerator, UINT64_C(1) << 24) :
                      pa_m5_rne_u64(numerator, UINT64_C(1) << 24);
    }
    publish(id, cycles() - start, sum, 8192);
  }
  for (unsigned id = 4; id < 8; ++id) {
    const double *source = id >= 6 ? ddr_scales : local_scales;
    uint32_t *out = id >= 6 ? ddr_multipliers : local_multipliers;
    uint32_t shift = 0; int status = 0;
    uint64_t start = cycles();
    for (unsigned repeat = 0; repeat < 8; ++repeat)
      status |= id & 1 ? pa_m5_affine_metadata(source, 512, out, &shift) :
                        pa_m5_baseline_affine_metadata(source, 512, out, &shift);
    uint64_t elapsed = cycles() - start, sum = shift;
    for (unsigned i = 0; i < 512; ++i) sum += out[i];
    publish(id, elapsed, status ? UINT64_MAX : sum, 4096);
  }
  volatile uint32_t *header = (volatile uint32_t *)TRACE;
  header[0] = UINT32_C(0x35425250); header[1] = 1; header[2] = 8;
  results[0] = 4;
  __asm__ volatile("fence rw,rw" ::: "memory"); REG(0x11000, 8) = 1;
  for (;;) __asm__ volatile("wfi");
}

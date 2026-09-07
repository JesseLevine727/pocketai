#include "pa_m5_hw.h"
#define REG(base, off) (*(volatile uint32_t *)((base) + (off)))
#define WORK UINT32_C(0x4f1f9000)
#define TRACE UINT32_C(0x4f5fa000)
static volatile uint32_t results[32] __attribute__((section(".results"))) = {0};
static pa_m5_hw_shared shared;
extern int pa_m5_requant_offload(const pa_m5_backend *, pa_m5_workspace *,
                                const int16_t *, uint32_t, uint32_t, int8_t *, double *);
static uint64_t cycles(void) {
  uint32_t high0, low, high1;
  do {
    __asm__ volatile("csrr %0,mcycleh" : "=r"(high0));
    __asm__ volatile("csrr %0,mcycle" : "=r"(low));
    __asm__ volatile("csrr %0,mcycleh" : "=r"(high1));
  } while (high0 != high1);
  return ((uint64_t)high0 << 32) | low;
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
  if (hart) { pa_m5_hw_service_hart1(&shared); for (;;) __asm__ volatile("wfi"); }
  pa_m5_hw_context hardware; pa_m5_backend backend; pa_m5_workspace workspace;
  pa_m5_hw_prepare_hart0(&hardware, &shared, 100000000);
  int status = pa_m5_hw_wait_hart1(&hardware);
  pa_m5_hw_backend_open(&backend, &hardware);
  pa_m5_workspace_open(&workspace, (void *)(WORK + 0x20000), 0x20000);
  int16_t *input = (int16_t *)(WORK + 0x3000);
  int8_t *reference = (int8_t *)(WORK + 0x10000), *candidate = (int8_t *)(WORK + 0x14000);
  double *reference_units = (double *)(WORK + 0x18000), *candidate_units = reference_units + 16;
  static const uint32_t columns[4] = {64, 768, 3072, 3072};
  static const uint32_t rows[4] = {1, 1, 1, 4};
  volatile uint32_t *header = (volatile uint32_t *)TRACE;
  for (uint32_t shape = 0; shape < 4 && !status; ++shape) {
    uint32_t count = columns[shape] * rows[shape];
    for (uint32_t i = 0; i < count; ++i) input[i] = (int16_t)(i * 101u + shape * 997u);
    input[0] = -32768; input[1] = 32767; input[2] = 0;
    for (uint32_t mode = 0; mode < 2; ++mode) {
      int8_t *out = mode ? candidate : reference;
      double *units = mode ? candidate_units : reference_units;
      uint32_t engine_before = shared.engine_cycles, jobs_before = shared.transfer_count;
      uint64_t start = cycles();
      for (uint32_t repeat = 0; repeat < 4 && !status; ++repeat) {
        status = mode ? pa_m5_requant_offload(&backend, &workspace, input, rows[shape], columns[shape], out, units) :
                        pa_m5_dynamic_quantize(input, rows[shape], columns[shape], out, units);
      }
      uint64_t elapsed = cycles() - start;
      uint32_t hash = UINT32_C(2166136261);
      for (uint32_t i = 0; i < count; ++i) hash = (hash ^ (uint8_t)out[i]) * UINT32_C(16777619);
      for (uint32_t row = 0; row < rows[shape]; ++row) {
        union { double value; uint64_t bits; } unit = {.value = units[row]};
        hash = (hash ^ (uint32_t)unit.bits) * UINT32_C(16777619);
        hash = (hash ^ (uint32_t)(unit.bits >> 32)) * UINT32_C(16777619);
      }
      volatile uint32_t *record = header + 8 + (shape*2+mode)*8;
      record[0] = shape*2+mode; record[1] = (uint32_t)elapsed; record[2] = (uint32_t)(elapsed >> 32);
      record[3] = hash; record[4] = count*4; record[5] = shared.engine_cycles-engine_before;
      record[6] = shared.transfer_count-jobs_before; record[7] = (uint32_t)status;
    }
    for (uint32_t i = 0; i < count; ++i) if (reference[i] != candidate[i]) status = -10;
    for (uint32_t row = 0; row < rows[shape]; ++row) {
      union { double value; uint64_t bits; } a = {.value=reference_units[row]}, b = {.value=candidate_units[row]};
      if (a.bits != b.bits) status = -11;
    }
  }
  header[0] = UINT32_C(0x31505152); header[1] = 1; header[2] = 8; header[3] = (uint32_t)status;
  results[0] = status ? 5 : 4;
  __asm__ volatile("fence rw,rw" ::: "memory"); REG(0x11000, 8) = 1;
  for (;;) __asm__ volatile("wfi");
}

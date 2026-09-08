#include "detail.h"
#if defined(PA_STARTUP_DIAGNOSTIC) && defined(__riscv)
typedef struct { uint64_t cycles; uint32_t calls, reserved; } record;
typedef struct { uint32_t magic, version, count, reserved; record records[START_DETAIL_COUNT]; } detail;
static volatile detail * const output = (volatile detail *)UINT32_C(0x4f624000);
typedef struct { uint64_t cycles, instructions; uint32_t calls, reserved; } leaf_record;
typedef struct { uint32_t magic, version, count, reserved; leaf_record records[2]; } leaf_detail;
static volatile leaf_detail * const leaf_output = (volatile leaf_detail *)UINT32_C(0x4f625000);
uint64_t pa_startup_begin(void) {
  uint32_t high0, low, high1;
  do {
    __asm__ volatile("csrr %0, mcycleh" : "=r"(high0));
    __asm__ volatile("csrr %0, mcycle" : "=r"(low));
    __asm__ volatile("csrr %0, mcycleh" : "=r"(high1));
  } while (high0 != high1);
  return ((uint64_t)high0 << 32) | low;
}
void pa_startup_reset(void) {
  output->magic = UINT32_C(0x37545350); output->version = 1;
  output->count = START_DETAIL_COUNT; output->reserved = 0;
  for (uint32_t i = 0; i < START_DETAIL_COUNT; ++i) {
    output->records[i].cycles = 0; output->records[i].calls = 0;
    output->records[i].reserved = 0;
  }
  leaf_output->magic = UINT32_C(0x3746504c); leaf_output->version = 1;
  leaf_output->count = 2; leaf_output->reserved = 0;
  for (uint32_t i = 0; i < 2; ++i) {
    leaf_output->records[i].cycles = 0; leaf_output->records[i].instructions = 0;
    leaf_output->records[i].calls = 0; leaf_output->records[i].reserved = 0;
  }
}
uint64_t pa_startup_instructions(void) {
  uint32_t high0, low, high1;
  do {
    __asm__ volatile("csrr %0, minstreth" : "=r"(high0));
    __asm__ volatile("csrr %0, minstret" : "=r"(low));
    __asm__ volatile("csrr %0, minstreth" : "=r"(high1));
  } while (high0 != high1);
  return ((uint64_t)high0<<32)|low;
}
void pa_startup_leaf_end(uint32_t worker, uint64_t start, uint64_t instructions) {
  uint64_t end = pa_startup_begin(), retired = pa_startup_instructions();
  /* Separate complete records, one writer per hart; caller joins before read. */
  leaf_output->records[worker].cycles += end-start;
  leaf_output->records[worker].instructions += retired-instructions;
  ++leaf_output->records[worker].calls;
}
void pa_startup_end(uint32_t kind, uint64_t start) {
  uint64_t end = pa_startup_begin();
  output->records[kind].cycles += end-start;
  ++output->records[kind].calls;
}
#endif

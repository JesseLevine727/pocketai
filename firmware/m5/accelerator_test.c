/* Transport/IRQ integration firmware, NOT the complete GPT-2 runtime.
 * Hart 0 prepares operands and checks/copies results; hart 1 alone schedules
 * real GEMM/SFPU descriptors and translated transfers. No in-run host service. */
#include <stdint.h>
#define REG(base, off) (*(volatile uint32_t *)((base) + (off)))
#define GEMM 0x00013000u
#define SFPU 0x00014000u
#define DMA  0x00015000u
#define MBOX 0x00012000u
#define A 0x40000ffcu
#define B 0x4000dffcu
#define C 0x4001affcu
#define D 0x40020ffcu
#define TRACE 0x40030000u
#define JOBS 9u
struct result {
  uint32_t state, errors, mailbox_irqs, dma_irqs, message, jobs, checks, route_checks;
  uint32_t cause, address, pc, cycle_start, cycle_end, gemm_irqs, sfpu_irqs, unexpected_irqs;
};
static volatile struct result results[2] __attribute__((section(".results"))) = {{0}, {0}};
_Static_assert(sizeof(struct result) == 64, "result ABI");
static uint32_t cycles(void) {
  uint32_t value; __asm__ volatile("csrr %0, mcycle" : "=r"(value)); return value;
}
static void check(uint32_t hart, int okay, uint32_t bit) {
  if (!okay) results[hart].errors |= bit;
}
static uint32_t dimension_k(uint32_t job) {
  static const uint32_t values[5] = {1, 3, 7, 768, 3072};
  return values[job - 1];
}
static uint32_t dimension_m(uint32_t job) { return job == 5 ? 16u : job == 1 ? 1u : 3u; }
static uint32_t output_words(uint32_t job) { return job <= 5 ? 16 * dimension_m(job) : job == 9 ? 1u : 3072u; }
static int32_t av(uint32_t row, uint32_t k) { return (int32_t)(row + 1) * ((int32_t)(k % 4) - 2); }
static int32_t bv(uint32_t col) { return (int32_t)(col % 7) - 3; }
static int32_t xval(uint32_t i) { return (int32_t)(i % 201) - 100; }
static int32_t yval(uint32_t i) { return (int32_t)(i % 129) - 64; }
static int32_t bias(uint32_t i) { return (int32_t)(i % 17) - 8; }
static int32_t rne(int32_t value, uint32_t shift) {
  uint32_t magnitude = (uint32_t)(value < 0 ? -value : value);
  uint32_t low = magnitude & ((1u << shift) - 1), high = magnitude >> shift;
  uint32_t half = 1u << (shift - 1);
  high += low > half || (low == half && (high & 1));
  return value < 0 ? -(int32_t)high : (int32_t)high;
}
static int32_t expected(uint32_t job, uint32_t index) {
  if (job <= 5) {
    uint32_t k = dimension_k(job), col = index % 16;
    if (col >= 13) return 0;
    int32_t sum = -(int32_t)(k / 4) * 2;
    for (uint32_t j = 0; j < k % 4; ++j) sum += (int32_t)j - 2;
    return (int32_t)(index / 16 + 1) * bv(col) * sum;
  }
  if (job == 6) return xval(index) + yval(index);
  if (job == 7) return rne(xval(index) * 3, 1) + bias(index);
  if (job == 8) {
    int32_t value = rne(xval(index) * 7, 3);
    return value > 127 ? 127 : value < -128 ? -128 : value;
  }
  return 32768;
}

void m5_memory_trap(void) __attribute__((interrupt("machine")));
void m5_memory_trap(void) {
  uint32_t hart, cause;
  __asm__ volatile("csrr %0, mhartid" : "=r"(hart));
  __asm__ volatile("csrr %0, mcause" : "=r"(cause));
  if (cause != 0x8000000bu) {
    results[hart].errors |= 0x80000000u;
    results[hart].cause = cause;
    __asm__ volatile("csrr %0, mtval" : "=r"(cause)); results[hart].address = cause;
    __asm__ volatile("csrr %0, mepc" : "=r"(cause)); results[hart].pc = cause;
    REG(0x11000u, 8) = 1;
    for (;;) __asm__ volatile("wfi");
  }
  uint32_t mask = hart == 0 ? 2u : 1u;
  uint32_t handled = 0;
  if (REG(MBOX, 8) & mask) {
    results[hart].message = REG(MBOX, hart == 0 ? 4u : 0u);
    REG(MBOX, 12) = mask;
    ++results[hart].mailbox_irqs;
    handled = 1;
  }
  if (hart == 1 && (REG(DMA, 4) & 4) && REG(DMA, 0x44)) {
    REG(DMA, 0x44) = 0;
    ++results[hart].dma_irqs;
    handled = 1;
  }
  if (hart == 1 && REG(GEMM, 0x40) && (REG(GEMM, 4) & 12)) {
    REG(GEMM, 0x40) = 0; ++results[hart].gemm_irqs; handled = 1;
  }
  if (hart == 1 && REG(SFPU, 0x40) && (REG(SFPU, 4) & 12)) {
    REG(SFPU, 0x40) = 0; ++results[hart].sfpu_irqs; handled = 1;
  }
  if (!handled) ++results[hart].unexpected_irqs;
}

static void prepare(uint32_t job) {
  if (job <= 5) {
    uint32_t k = dimension_k(job), m = dimension_m(job), stride = (k + 3) / 4;
    for (uint32_t row = 0; row < m; ++row) for (uint32_t w = 0; w < stride; ++w) {
      uint32_t packed = 0;
      for (uint32_t lane = 0; lane < 4; ++lane)
        if (w * 4 + lane < k) packed |= (uint32_t)(uint8_t)av(row, w * 4 + lane) << (lane * 8);
      REG(A, (row * stride + w) * 4) = packed;
    }
    for (uint32_t p = 0; p < k; ++p) for (uint32_t group = 0; group < 4; ++group) {
      uint32_t packed = 0;
      for (uint32_t lane = 0; lane < 4; ++lane) {
        uint32_t col = group * 4 + lane;
        if (col < 13) packed |= (uint32_t)(uint8_t)bv(col) << (lane * 8);
      }
      REG(B, (p * 4 + group) * 4) = packed;
    }
  } else for (uint32_t i = 0; i < output_words(job); ++i) {
    // Softmax packet bit 16 is validity; raw score zero alone is masked.
    REG(A, i * 4) = job == 9 ? 0x10000u : (uint32_t)xval(i);
    if (job == 6 || job == 7) REG(B, i * 4) = job == 6 ? (uint32_t)yval(i) : 3u;
    if (job == 7) REG(C, i * 4) = (uint32_t)bias(i);
  }
  for (uint32_t i = 0; i < output_words(job); ++i) REG(D, i * 4) = 0xa5a5a5a5u;
}

static void schedule(uint32_t job) {
  uint32_t words[3] = {0, 0, 0}, route = job <= 5 ? 0u : 1u;
  REG(SFPU, 0x50) = route;
  if (job <= 5) {
    uint32_t k = dimension_k(job), m = dimension_m(job);
    REG(GEMM, 8) = m; REG(GEMM, 12) = 13; REG(GEMM, 16) = k;
    REG(GEMM, 20) = 0x100; REG(GEMM, 24) = job;
    REG(GEMM, 0x40) = 1; REG(GEMM, 28) = 1;
    words[0] = m * ((k + 3) / 4); words[1] = k * 4;
  } else {
    uint32_t op = job == 6 ? 7u : job == 7 ? 4u : job == 8 ? 5u : 3u;
    REG(SFPU, 8) = op; REG(SFPU, 12) = output_words(job);
    REG(SFPU, 16) = job == 7 ? 1u : job == 8 ? 3u : 0u;
    REG(SFPU, 20) = job == 8 ? 7u : 0u;
    REG(SFPU, 24) = job; REG(SFPU, 0x40) = 1; REG(SFPU, 28) = 1;
    words[0] = output_words(job);
    if (job == 6 || job == 7) words[1] = words[0];
    if (job == 7) words[2] = words[0];
  }
  REG(DMA, 8) = A; REG(DMA, 12) = words[0];
  REG(DMA, 16) = words[1] ? B : 0u; REG(DMA, 20) = words[1];
  REG(DMA, 24) = words[2] ? C : 0u; REG(DMA, 28) = words[2];
  REG(DMA, 32) = D; REG(DMA, 36) = output_words(job);
  REG(DMA, 40) = job; REG(DMA, 44) = 20000000;
  REG(DMA, 0x44) = 1; REG(DMA, 0x30) = 1;
  // Completion decision depends on an actual interrupt, not polling DONE.
  while (results[1].dma_irqs != job) __asm__ volatile("nop");
  check(1, REG(DMA, 0x38) == 0 && REG(DMA, 0x34) == job, 1);
  check(1, REG(DMA, 0x3c) == words[0] + words[1] + words[2] &&
           REG(DMA, 0x40) == output_words(job), 2);
  uint32_t engine = route ? SFPU : GEMM;
  check(1, (REG(engine, 4) & 12) == 4 && REG(engine, 32) == job, 4);
  // The operator is done, but pending DMA completion still owns the route.
  REG(SFPU, 0x50) = !route;
  check(1, REG(SFPU, 0x50) == route && REG(SFPU, 0x38) == 9, 8);
  ++results[1].route_checks;
  REG(DMA, 0x30) = 2;
  REG(engine, 28) = 2; REG(SFPU, 28) = 2;
  check(1, REG(DMA, 4) == 1 && REG(DMA, 0x50) == job && REG(DMA, 0x54) == job, 16);
}

void m5_memory_main(uint32_t hart) {
  results[hart].cycle_start = cycles(); results[hart].state = 1;
  __asm__ volatile("li t0, 0x800\ncsrw mie, t0\ncsrsi mstatus, 8" ::: "t0", "memory");
  if (hart == 1) {
    for (uint32_t job = 1; job <= JOBS; ++job) {
      while (results[1].message != job) __asm__ volatile("nop");
      schedule(job); ++results[1].jobs;
      __asm__ volatile("fence rw, rw" ::: "memory"); REG(MBOX, 4) = job;
    }
    results[1].cycle_end = cycles(); results[1].state = 2;
  } else {
    while (results[1].state != 1) __asm__ volatile("nop");
    for (uint32_t job = 1; job <= JOBS; ++job) {
      prepare(job);
      __asm__ volatile("fence rw, rw" ::: "memory"); REG(MBOX, 0) = job;
      // Independent core DDR traffic competes with the bulk mover.
      uint32_t sequence = 0;
      while (results[0].message != job) {
        REG(0x4002f000u, 0) = sequence;
        check(0, REG(0x4002f000u, 0) == sequence, 2); ++sequence;
      }
      for (uint32_t i = 0; i < output_words(job); ++i) {
        uint32_t got = REG(D, i * 4);
        check(0, got == (uint32_t)expected(job, i), 1);
        REG(TRACE + (job - 1) * 0x4000u, i * 4) = got; ++results[0].checks;
      }
      ++results[0].jobs;
    }
    while (results[1].state != 2) __asm__ volatile("nop");
    results[0].cycle_end = cycles(); results[0].state = 3; REG(0x11000u, 8) = 1;
  }
  for (;;) __asm__ volatile("wfi");
}

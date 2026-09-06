/* Short OPT5 decode-only diagnostic; baseline numerical/runtime sources unchanged.
 * Profile storage stays on chip until inference ends. A9 never serves tensors.
 */
#include "pa_m5_hw.h"
#include "pa_m5_runtime.h"

#define REG(base, off) (*(volatile uint32_t *)((base) + (off)))
#define ARENA ((void *)UINT32_C(0x40000000))
#define WORK UINT32_C(0x4f1f9000)
#define TRACE UINT32_C(0x4f5fa000)
#define CONTROL_MAGIC UINT32_C(0x3554504f)
#define PROFILE_MAGIC UINT32_C(0x35524650)
#define LOGITS_OFFSET UINT32_C(0x3000)
#define RECORD_OFFSET UINT32_C(0x20000)
#define MAX_RECORDS 104u

typedef struct {
  volatile uint32_t magic, version, request, command, count, generated, flags, deadline;
  volatile uint32_t state, error, past, generated_count, reserved[11], ready, hart_error;
} control_t;
typedef struct {
  volatile uint32_t state, error, cause, address, pc, reserved[11];
} result_t;
typedef struct {
  uint32_t kind, layer;
  uint64_t elapsed, service, gemm, sfpu;
  uint32_t jobs, input_words, output_words, reserved;
} record_t;
_Static_assert(sizeof(control_t) == 100, "control size");
_Static_assert(sizeof(result_t) == 64, "trap record size");
_Static_assert(sizeof(record_t) == 56, "profile record size");

static result_t results[2] __attribute__((section(".results"))) = {{0}, {0}};
static pa_m5_hw_shared shared;
static pa_m5_backend underlying;
static record_t records[MAX_RECORDS];
static uint32_t record_count, last_jobs, last_input, last_output;
static uint64_t service_cycles, gemm_cycles, sfpu_cycles;
static uint64_t previous_time, previous_service, previous_gemm, previous_sfpu;

static void fence(void) { __asm__ volatile("fence rw, rw" ::: "memory"); }
static uint64_t cycles(void) {
  uint32_t high0, low, high1;
  do {
    __asm__ volatile("csrr %0, mcycleh" : "=r"(high0));
    __asm__ volatile("csrr %0, mcycle" : "=r"(low));
    __asm__ volatile("csrr %0, mcycleh" : "=r"(high1));
  } while (high0 != high1);
  return ((uint64_t)high0 << 32) | low;
}
static int prof_gemm(void *ctx, uint32_t rows, uint32_t k, uint32_t n,
                      const int8_t *a, const int8_t *tile, int32_t *out) {
  (void)ctx;
  uint32_t before = shared.engine_cycles;
  uint64_t start = cycles();
  int result = underlying.gemm_tile(underlying.context, rows, k, n, a, tile, out);
  uint64_t end = cycles();
  service_cycles += end - start;
  gemm_cycles += (uint32_t)(shared.engine_cycles - before);
  return result;
}
static int prof_sfpu(void *ctx, uint32_t op, uint32_t length, uint32_t shift,
                      uint32_t multiplier, const int32_t *p0, const int32_t *p1,
                      const int32_t *p2, int32_t *out) {
  (void)ctx;
  uint32_t before = shared.engine_cycles;
  uint64_t start = cycles();
  int result = underlying.sfpu(underlying.context, op, length, shift, multiplier,
                               p0, p1, p2, out);
  uint64_t end = cycles();
  service_cycles += end - start;
  sfpu_cycles += (uint32_t)(shared.engine_cycles - before);
  return result;
}
static int checkpoint(void *ctx, uint32_t kind, uint32_t layer,
                       const int16_t *values, const uint32_t *exponents,
                       uint32_t rows, uint32_t columns, const double *scale) {
  (void)ctx; (void)values; (void)exponents; (void)rows; (void)columns; (void)scale;
  uint64_t now = cycles();
  if (record_count >= MAX_RECORDS) return -1;
  record_t *r = &records[record_count++];
  r->kind = kind; r->layer = layer;
  r->elapsed = now - previous_time;
  r->service = service_cycles - previous_service;
  r->gemm = gemm_cycles - previous_gemm; r->sfpu = sfpu_cycles - previous_sfpu;
  r->jobs = shared.transfer_count - last_jobs;
  r->input_words = shared.input_words - last_input;
  r->output_words = shared.output_words - last_output; r->reserved = 0;
  previous_time = now; previous_service = service_cycles;
  previous_gemm = gemm_cycles; previous_sfpu = sfpu_cycles;
  last_jobs = shared.transfer_count; last_input = shared.input_words;
  last_output = shared.output_words;
  return 0;
}
static void fail(control_t *control, uint32_t code) {
  control->error = code; control->state = 5;
  fence(); REG(UINT32_C(0x11000), 8) = 1;
}
void m5_memory_trap(void) __attribute__((interrupt("machine")));
void m5_memory_trap(void) {
  uint32_t hart, value;
  __asm__ volatile("csrr %0, mhartid" : "=r"(hart));
  results[hart].error = UINT32_C(0x80000000);
  __asm__ volatile("csrr %0, mcause" : "=r"(value)); results[hart].cause = value;
  __asm__ volatile("csrr %0, mtval" : "=r"(value)); results[hart].address = value;
  __asm__ volatile("csrr %0, mepc" : "=r"(value)); results[hart].pc = value;
  results[hart].state = 5; fence(); REG(UINT32_C(0x11000), 8) = 1;
  for (;;) __asm__ volatile("wfi");
}
static void run(void) {
  control_t *control = (control_t *)WORK;
  const uint32_t *token = (const uint32_t *)(WORK + 0x1000);
  if (control->magic != CONTROL_MAGIC || control->version != 1 ||
      control->command != 2 || control->count != 1 || control->generated != 1 ||
      control->flags > 1 || !control->deadline || !control->past ||
      control->past >= 1024 || control->state || control->error || *token >= 50257) {
    fail(control, 1); return;
  }
  control->state = 1; control->ready = 1;
  pa_m5_model model;
  if (pa_m5_model_open(&model, ARENA, PA_M5_ARENA_BYTES)) { fail(control, 2); return; }
  pa_m5_hw_context hardware;
  pa_m5_hw_prepare_hart0(&hardware, &shared, control->deadline);
  if (pa_m5_hw_wait_hart1(&hardware)) { fail(control, 3); return; }
  pa_m5_hw_backend_open(&underlying, &hardware);
  pa_m5_workspace workspace;
  pa_m5_workspace_open(&workspace, (void *)(WORK + 0x3000), 0x400000 - 0x3000);
  pa_m5_cache cache; pa_m5_cache_open(&cache, ARENA);
  pa_m5_runtime runtime = {&model, underlying, &workspace, &cache, 0, 0};
  if (control->flags) {
    runtime.backend.context = 0; runtime.backend.gemm_tile = prof_gemm;
    runtime.backend.sfpu = prof_sfpu; runtime.trace = checkpoint;
  }
  int16_t *logits = (int16_t *)(TRACE + LOGITS_OFFSET);
  uint32_t exponent = 0;
  control->ready = 3; control->state = 3; fence();
  uint64_t start = cycles(); previous_time = start;
  int status = pa_m5_forward_chunk(&runtime, token, 1, control->past, logits, &exponent);
  if (status) { fail(control, 0x1000 - (uint32_t)status); return; }
  uint32_t selected = 0;
  for (uint32_t i = 1; i < 50257; ++i) if (logits[i] > logits[selected]) selected = i;
  *(uint32_t *)(WORK + 0x2000) = selected;
  control->generated_count = 1; ++control->past; fence();
  if (control->flags && checkpoint(0, 12, 0, 0, 0, 0, 0, 0)) { fail(control, 4); return; }
  uint64_t end = cycles();
  /* Publication is outside the model interval, inside the host request. */
  volatile uint32_t *header = (volatile uint32_t *)TRACE;
  for (uint32_t i = 0; i < 64; ++i) header[i] = 0;
  header[0] = PROFILE_MAGIC; header[1] = 1; header[2] = LOGITS_OFFSET;
  header[3] = 50257; header[4] = exponent; header[5] = record_count;
  header[6] = RECORD_OFFSET; header[7] = sizeof(record_t);
  header[8] = (uint32_t)start; header[9] = (uint32_t)(start >> 32);
  header[10] = (uint32_t)end; header[11] = (uint32_t)(end >> 32);
  header[12] = shared.transfer_count; header[13] = shared.input_words;
  header[14] = shared.output_words; header[15] = workspace.high_water;
  header[16] = (uint32_t)service_cycles; header[17] = (uint32_t)(service_cycles >> 32);
  header[18] = (uint32_t)gemm_cycles; header[19] = (uint32_t)(gemm_cycles >> 32);
  header[20] = (uint32_t)sfpu_cycles; header[21] = (uint32_t)(sfpu_cycles >> 32);
  header[22] = shared.engine_cycles;
  const uint32_t *source = (const uint32_t *)records;
  volatile uint32_t *destination = (volatile uint32_t *)(TRACE + RECORD_OFFSET);
  for (uint32_t i = 0; i < record_count * sizeof(record_t) / 4; ++i) destination[i] = source[i];
  results[0].state = 4; control->state = 4;
  fence(); REG(UINT32_C(0x11000), 8) = 1;
}
void m5_memory_main(uint32_t hart) {
  if (hart == 1) {
    results[1].state = 1; pa_m5_hw_service_hart1(&shared);
  } else run();
  for (;;) __asm__ volatile("wfi");
}

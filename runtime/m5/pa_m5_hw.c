#include "pa_m5_hw.h"

#define PA_M5_GEMM UINT32_C(0x00013000)
#define PA_M5_SFPU UINT32_C(0x00014000)
#define PA_M5_DMA  UINT32_C(0x00015000)
#define PA_M5_MBOX UINT32_C(0x00012000)
#define REG(base, offset) (*(volatile uint32_t *)((base) + (offset)))

static void fence(void) { __asm__ volatile("fence rw, rw" ::: "memory"); }

static int arena_range(const void *pointer, uint32_t words) {
  uintptr_t address = (uintptr_t)pointer;
  uint64_t end = (uint64_t)address + (uint64_t)words * 4;
  return address >= UINT32_C(0x40000000) && !(address & 3) && words &&
         end <= UINT64_C(0x50000000);
}

static int submit(pa_m5_hw_context *context) {
  pa_m5_hw_shared *shared = context->shared;
  uint32_t sequence = shared->request_sequence + 1;
  if (!sequence) sequence = 1;
  shared->status = -1;
  shared->deadline = context->deadline;
  fence();
  shared->request_sequence = sequence;
  fence();
  REG(PA_M5_MBOX, 0) = sequence;
  while (!(REG(PA_M5_MBOX, 8) & 2u)) __asm__ volatile("nop");
  uint32_t returned = REG(PA_M5_MBOX, 4);
  REG(PA_M5_MBOX, 12) = 2;
  fence();
  return returned == sequence && shared->completion_sequence == sequence ?
         shared->status : -1;
}

static int hardware_gemm(void *opaque, uint32_t rows, uint32_t k, uint32_t n,
                         const int8_t *a, const int8_t *tile,
                         int32_t *output) {
  pa_m5_hw_context *context = opaque;
  uint32_t a_words = rows * ((k + 3) / 4), tile_words = k * 4;
  uint32_t output_words = rows * 16;
  if (!context || !context->shared || !rows || rows > 16 || !k || k > 3072 ||
      !n || n > 16 || !arena_range(a, a_words) ||
      !arena_range(tile, tile_words) || !arena_range(output, output_words)) return -1;
  pa_m5_hw_shared *shared = context->shared;
  shared->kind = PA_M5_HW_GEMM;
  shared->rows = rows; shared->k = k; shared->n = n;
  shared->operation = 0; shared->length = 0; shared->shift = 0;
  shared->multiplier = 0;
  shared->source[0] = (uint32_t)(uintptr_t)a;
  shared->source_words[0] = a_words;
  shared->source[1] = (uint32_t)(uintptr_t)tile;
  shared->source_words[1] = tile_words;
  shared->source[2] = 0; shared->source_words[2] = 0;
  shared->destination = (uint32_t)(uintptr_t)output;
  shared->destination_words = output_words;
  return submit(context);
}

static uint32_t sfpu_planes(uint32_t operation) {
  if (operation == PA_M5_SFPU_LAYERNORM || operation == PA_M5_SFPU_AFFINE ||
      operation == PA_M5_SFPU_AFFINE_GELU) return 3;
  if (operation == PA_M5_SFPU_ADD) return 2;
  return 1;
}

static int hardware_sfpu(void *opaque, uint32_t operation, uint32_t length,
                         uint32_t shift, uint32_t multiplier,
                         const int32_t *plane0, const int32_t *plane1,
                         const int32_t *plane2, int32_t *output) {
  pa_m5_hw_context *context = opaque;
  uint32_t planes = sfpu_planes(operation);
  if (!context || !context->shared || operation < PA_M5_SFPU_GELU ||
      operation > PA_M5_SFPU_ADD || !length || length > 3072 ||
      (operation == PA_M5_SFPU_SOFTMAX && length > 1024) ||
      !arena_range(plane0, length) || !arena_range(output, length) ||
      (planes >= 2 && !arena_range(plane1, length)) ||
      (planes == 3 && !arena_range(plane2, length))) return -1;
  pa_m5_hw_shared *shared = context->shared;
  shared->kind = PA_M5_HW_SFPU;
  shared->rows = 0; shared->k = 0; shared->n = 0;
  shared->operation = operation; shared->length = length;
  shared->shift = shift; shared->multiplier = multiplier;
  shared->source[0] = (uint32_t)(uintptr_t)plane0;
  shared->source_words[0] = length;
  shared->source[1] = planes >= 2 ? (uint32_t)(uintptr_t)plane1 : 0;
  shared->source_words[1] = planes >= 2 ? length : 0;
  shared->source[2] = planes == 3 ? (uint32_t)(uintptr_t)plane2 : 0;
  shared->source_words[2] = planes == 3 ? length : 0;
  shared->destination = (uint32_t)(uintptr_t)output;
  shared->destination_words = length;
  return submit(context);
}

void pa_m5_hw_prepare_hart0(pa_m5_hw_context *context,
                            pa_m5_hw_shared *shared, uint32_t deadline) {
  shared->magic = 0; shared->hart1_ready = 0;
  shared->request_sequence = 0; shared->completion_sequence = 0;
  shared->status = 0; shared->transfer_count = 0;
  shared->input_words = 0; shared->output_words = 0;
  shared->engine_cycles = 0; shared->engine_work_low = 0;
  shared->engine_work_high = 0;
  REG(PA_M5_MBOX, 12) = 2;
  context->shared = shared; context->deadline = deadline;
  fence(); shared->magic = PA_M5_HW_SHARED_MAGIC; fence();
}

int pa_m5_hw_wait_hart1(pa_m5_hw_context *context) {
  if (!context || !context->shared) return -1;
  while (!context->shared->hart1_ready) __asm__ volatile("nop");
  fence(); return 0;
}

void pa_m5_hw_backend_open(pa_m5_backend *backend, pa_m5_hw_context *context) {
  backend->context = context;
  backend->gemm_tile = hardware_gemm;
  backend->sfpu = hardware_sfpu;
}

static int execute(pa_m5_hw_shared *shared, uint32_t sequence) {
  uint32_t engine, expected_input;
  REG(PA_M5_SFPU, 0x50) = shared->kind == PA_M5_HW_SFPU;
  if (shared->kind == PA_M5_HW_GEMM) {
    engine = PA_M5_GEMM;
    REG(engine, 8) = shared->rows; REG(engine, 12) = shared->n;
    REG(engine, 16) = shared->k; REG(engine, 20) = 0x100;
    REG(engine, 24) = sequence; REG(engine, 0x40) = 0;
    REG(engine, 28) = 1;
    expected_input = shared->source_words[0] + shared->source_words[1];
  } else if (shared->kind == PA_M5_HW_SFPU) {
    engine = PA_M5_SFPU;
    REG(engine, 8) = shared->operation; REG(engine, 12) = shared->length;
    REG(engine, 16) = shared->shift; REG(engine, 20) = shared->multiplier;
    REG(engine, 24) = sequence; REG(engine, 0x40) = 0;
    REG(engine, 28) = 1;
    expected_input = shared->source_words[0] + shared->source_words[1] +
                     shared->source_words[2];
  } else return -2;
  if (!(REG(engine, 4) & 2u)) return -3;

  REG(PA_M5_DMA, 8) = shared->source[0];
  REG(PA_M5_DMA, 12) = shared->source_words[0];
  REG(PA_M5_DMA, 16) = shared->source[1];
  REG(PA_M5_DMA, 20) = shared->source_words[1];
  REG(PA_M5_DMA, 24) = shared->source[2];
  REG(PA_M5_DMA, 28) = shared->source_words[2];
  REG(PA_M5_DMA, 32) = shared->destination;
  REG(PA_M5_DMA, 36) = shared->destination_words;
  REG(PA_M5_DMA, 40) = sequence;
  REG(PA_M5_DMA, 44) = shared->deadline;
  REG(PA_M5_DMA, 0x44) = 0;
  REG(PA_M5_DMA, 0x30) = 1;
  while (!(REG(PA_M5_DMA, 4) & (4u | 8u | 16u | 32u | 64u)))
    __asm__ volatile("nop");
  uint32_t dma_status = REG(PA_M5_DMA, 4), engine_status = REG(engine, 4);
  int status = 0;
  if (!(dma_status & 4u) || (engine_status & 8u) ||
      REG(PA_M5_DMA, 0x38) || REG(PA_M5_DMA, 0x34) != sequence ||
      REG(engine, 0x20) != sequence || REG(PA_M5_DMA, 0x3c) != expected_input ||
      REG(PA_M5_DMA, 0x40) != shared->destination_words) status = -4;
  shared->input_words += REG(PA_M5_DMA, 0x3c);
  shared->output_words += REG(PA_M5_DMA, 0x40);
  shared->engine_cycles += REG(engine, 0x24);
  uint64_t work = shared->kind == PA_M5_HW_GEMM ?
      (uint64_t)shared->rows * shared->n * shared->k : shared->length;
  uint64_t total = ((uint64_t)shared->engine_work_high << 32) |
                   shared->engine_work_low;
  total += work;
  shared->engine_work_low = (uint32_t)total;
  shared->engine_work_high = (uint32_t)(total >> 32);
  ++shared->transfer_count;
  REG(PA_M5_DMA, 0x30) = 2;
  REG(engine, 28) = 2;
  if (engine != PA_M5_SFPU) REG(PA_M5_SFPU, 28) = 2;
  return status;
}

void pa_m5_hw_service_hart1(pa_m5_hw_shared *shared) {
  REG(PA_M5_MBOX, 12) = 1;
  while (shared->magic != PA_M5_HW_SHARED_MAGIC) __asm__ volatile("nop");
  fence(); shared->hart1_ready = 1; fence();
  for (;;) {
    while (!(REG(PA_M5_MBOX, 8) & 1u)) __asm__ volatile("nop");
    uint32_t sequence = REG(PA_M5_MBOX, 0);
    REG(PA_M5_MBOX, 12) = 1;
    fence();
    int status = sequence && sequence == shared->request_sequence ?
                 execute(shared, sequence) : -1;
    shared->status = status;
    fence(); shared->completion_sequence = sequence; fence();
    REG(PA_M5_MBOX, 4) = sequence;
  }
}

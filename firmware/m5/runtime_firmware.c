/* Autonomous M5 GPT-2 runtime. The A9 provisions bytes and starts the harts;
 * both model scheduling and every accelerator transfer remain on the Ibex pair. */
#include "pa_m5_hw.h"
#include "pa_m5_runtime.h"
#include <stdint.h>

#define REG(base, offset) (*(volatile uint32_t *)((base) + (offset)))
#define PA_M5_CONSOLE UINT32_C(0x00011000)
#define PA_M5_ARENA ((void *)UINT32_C(0x40000000))
#define PA_M5_WORK_BASE UINT32_C(0x4f1f9000)
#define PA_M5_WORK_BYTES UINT32_C(0x00400000)
#define PA_M5_TRACE_BASE UINT32_C(0x4f5fa000)
#define PA_M5_TRACE_BYTES UINT32_C(0x00800000)
#define PA_M5_LOGITS_OFFSET UINT32_C(0x00003000)
#define PA_M5_RECORD_OFFSET UINT32_C(0x0001c000)
#define PA_M5_CONTROL_MAGIC UINT32_C(0x35545250)
#define PA_M5_TRACE_MAGIC UINT32_C(0x35435254)

typedef struct {
  volatile uint32_t magic, version, request_id, command;
  volatile uint32_t prompt_count, generation_count, flags, deadline;
  volatile uint32_t state, error, cache_valid, generated_count;
  volatile uint32_t current_layer, current_operator;
  volatile uint32_t transfers_accepted, transfers_completed;
  volatile uint32_t cycle_start, cycle_end, work_high_water, trace_bytes;
  volatile uint32_t tensor_bytes_read, tensor_bytes_written, selected_token;
  volatile uint32_t hart_ready, hart_error;
} pa_m5_control;

typedef struct {
  volatile uint32_t state, error, cause, address, pc, cycle_start, cycle_end;
  volatile uint32_t transfers, input_words, output_words, engine_cycles;
  volatile uint32_t work_low, work_high, reserved[3];
} pa_m5_firmware_result;

typedef struct {
  uint32_t kind, layer, rows, columns, exponent_bytes, value_bytes;
  uint32_t reserved[2];
} pa_m5_trace_record;

typedef struct {
  volatile uint32_t *header;
  uint32_t cursor;
  uint32_t records;
  uint32_t enabled;
} pa_m5_trace_context;

static volatile pa_m5_hw_shared shared_job;
static volatile pa_m5_firmware_result results[2]
    __attribute__((section(".results"))) = {{0}, {0}};
_Static_assert(sizeof(pa_m5_control) == 100, "control ABI");
_Static_assert(sizeof(pa_m5_firmware_result) == 64, "result ABI");
_Static_assert(sizeof(pa_m5_trace_record) == 32, "trace record ABI");

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

static void finish_error(pa_m5_control *control, uint32_t error) {
  control->error = error; control->state = 5;
  fence(); REG(PA_M5_CONSOLE, 8) = 1;
}

void m5_memory_trap(void) __attribute__((interrupt("machine")));
void m5_memory_trap(void) {
  uint32_t hart, value;
  __asm__ volatile("csrr %0, mhartid" : "=r"(hart));
  results[hart].error = UINT32_C(0x80000000);
  __asm__ volatile("csrr %0, mcause" : "=r"(value)); results[hart].cause = value;
  __asm__ volatile("csrr %0, mtval" : "=r"(value)); results[hart].address = value;
  __asm__ volatile("csrr %0, mepc" : "=r"(value)); results[hart].pc = value;
  results[hart].state = 5; fence(); REG(PA_M5_CONSOLE, 8) = 1;
  for (;;) __asm__ volatile("wfi");
}

static int wanted_trace(uint32_t kind, uint32_t layer) {
  return kind == PA_M5_TRACE_EMBEDDING ||
         (layer == 0 && (kind == PA_M5_TRACE_QKV ||
                         kind == PA_M5_TRACE_CONTEXT ||
                         kind == PA_M5_TRACE_OUTPUT)) ||
         (layer == 11 && kind == PA_M5_TRACE_OUTPUT);
}

static int capture_trace(void *opaque, uint32_t kind, uint32_t layer,
                         const int16_t *values, const uint32_t *exponents,
                         uint32_t rows, uint32_t columns,
                         const double *channel_scale) {
  pa_m5_trace_context *trace = opaque;
  (void)channel_scale;
  if (!trace->enabled || !wanted_trace(kind, layer)) return 0;
  uint32_t exponent_bytes = rows * 4, value_bytes = rows * columns * 2;
  uint32_t end = trace->cursor + sizeof(pa_m5_trace_record) +
                 exponent_bytes + value_bytes;
  end = (end + 63) & ~UINT32_C(63);
  if (end > PA_M5_TRACE_BYTES) return -1;
  pa_m5_trace_record *record = (pa_m5_trace_record *)(PA_M5_TRACE_BASE + trace->cursor);
  record->kind = kind; record->layer = layer; record->rows = rows;
  record->columns = columns; record->exponent_bytes = exponent_bytes;
  record->value_bytes = value_bytes; record->reserved[0] = 0; record->reserved[1] = 0;
  uint8_t *destination = (uint8_t *)(record + 1);
  for (uint32_t i = 0; i < rows; ++i) {
    uint32_t value = exponents ? exponents[i] : 0;
    for (uint32_t byte = 0; byte < 4; ++byte)
      destination[i*4+byte] = (uint8_t)(value >> (byte*8));
  }
  destination += exponent_bytes;
  for (uint32_t i = 0; i < rows*columns; ++i) {
    uint16_t value = (uint16_t)values[i];
    destination[i*2] = (uint8_t)value;
    destination[i*2+1] = (uint8_t)(value >> 8);
  }
  trace->cursor = end; ++trace->records;
  trace->header[7] = trace->records;
  return 0;
}

static int validate_request(const pa_m5_control *control) {
  if (control->magic != PA_M5_CONTROL_MAGIC || control->version != 1 ||
      control->command != 1 || control->state != 0 || control->error ||
      control->flags > 1 || !control->deadline || !control->prompt_count ||
      !control->generation_count || control->prompt_count > 1024 ||
      control->generation_count > 1024 - control->prompt_count) return -1;
  const uint32_t *tokens = (const uint32_t *)(PA_M5_WORK_BASE + 0x1000);
  for (uint32_t i = 0; i < control->prompt_count; ++i)
    if (tokens[i] >= 50257) return -1;
  return 0;
}

static void run_hart0(void) {
  pa_m5_control *control = (pa_m5_control *)PA_M5_WORK_BASE;
  results[0].state = 1;
  if (validate_request(control)) { finish_error(control, 1); return; }
  control->state = 1; control->hart_ready = 1;

  pa_m5_model model;
  if (pa_m5_model_open(&model, PA_M5_ARENA, PA_M5_ARENA_BYTES)) {
    finish_error(control, 2); return;
  }
  pa_m5_hw_context hardware;
  pa_m5_hw_prepare_hart0(&hardware, (pa_m5_hw_shared *)&shared_job,
                         control->deadline);
  if (pa_m5_hw_wait_hart1(&hardware)) { finish_error(control, 3); return; }
  control->hart_ready = 3; control->state = 2; fence();

  pa_m5_workspace workspace;
  pa_m5_workspace_open(&workspace, (void *)(PA_M5_WORK_BASE + 0x3000),
                       PA_M5_WORK_BYTES - 0x3000);
  pa_m5_cache cache;
  pa_m5_cache_open(&cache, PA_M5_ARENA);
  pa_m5_runtime runtime;
  runtime.model = &model; runtime.workspace = &workspace; runtime.cache = &cache;
  pa_m5_hw_backend_open(&runtime.backend, &hardware);

  volatile uint32_t *trace_header = (volatile uint32_t *)PA_M5_TRACE_BASE;
  for (uint32_t i = 0; i < 64; ++i) trace_header[i] = 0;
  trace_header[0] = PA_M5_TRACE_MAGIC; trace_header[1] = 1;
  trace_header[2] = PA_M5_LOGITS_OFFSET; trace_header[3] = 50257;
  trace_header[6] = PA_M5_RECORD_OFFSET;
  pa_m5_trace_context trace = {trace_header, PA_M5_RECORD_OFFSET, 0,
                               control->flags & 1u};
  runtime.trace_context = &trace; runtime.trace = capture_trace;
  int16_t *logits = (int16_t *)(PA_M5_TRACE_BASE + PA_M5_LOGITS_OFFSET);
  uint32_t logits_exponent = 0;
  const uint32_t *prompt = (const uint32_t *)(PA_M5_WORK_BASE + 0x1000);
  uint32_t *generated = (uint32_t *)(PA_M5_WORK_BASE + 0x2000);
  volatile uint32_t *timings = trace_header + 64;

  control->state = 3;
  uint64_t run_start = cycles(); control->cycle_start = (uint32_t)run_start;
  uint64_t interval = cycles();
  int status = pa_m5_prefill(&runtime, prompt, control->prompt_count, 0,
                             logits, &logits_exponent);
  uint64_t now = cycles();
  trace_header[20] = (uint32_t)(now - interval);
  trace_header[21] = (uint32_t)((now - interval) >> 32);
  interval = run_start;
  runtime.trace = 0;
  if (status) { finish_error(control, UINT32_C(0x1000) - (uint32_t)status); return; }
  uint32_t committed = control->prompt_count;
  control->cache_valid = committed;
  for (uint32_t step = 0; step < control->generation_count; ++step) {
    uint32_t selected = 0;
    for (uint32_t token = 1; token < 50257; ++token)
      if (logits[token] > logits[selected]) selected = token;
    generated[step] = selected; control->selected_token = selected;
    control->generated_count = step + 1; fence();
    now = cycles();
    timings[step*2] = (uint32_t)(now - interval);
    timings[step*2+1] = (uint32_t)((now - interval) >> 32);
    trace_header[5] = step + 1;
    if (step == 0) {
      uint64_t first_token = now;
      trace_header[18] = (uint32_t)first_token;
      trace_header[19] = (uint32_t)(first_token >> 32);
    }
    if (step + 1 < control->generation_count) {
      interval = now;
      status = pa_m5_forward_chunk(&runtime, &generated[step], 1, committed,
                                   logits, &logits_exponent);
      if (status) { finish_error(control, UINT32_C(0x2000) - (uint32_t)status); return; }
      ++committed; control->cache_valid = committed;
    }
  }
  uint64_t run_end = cycles();
  trace_header[4] = logits_exponent; trace_header[8] = (uint32_t)run_start;
  trace_header[9] = (uint32_t)(run_start >> 32); trace_header[10] = (uint32_t)run_end;
  trace_header[11] = (uint32_t)(run_end >> 32);
  trace_header[12] = shared_job.transfer_count;
  trace_header[13] = shared_job.input_words; trace_header[14] = shared_job.output_words;
  trace_header[15] = shared_job.engine_cycles;
  trace_header[16] = shared_job.engine_work_low; trace_header[17] = shared_job.engine_work_high;
  control->transfers_accepted = shared_job.transfer_count;
  control->transfers_completed = shared_job.transfer_count;
  control->tensor_bytes_read = shared_job.input_words * 4;
  control->tensor_bytes_written = shared_job.output_words * 4;
  control->work_high_water = workspace.high_water;
  control->trace_bytes = trace.cursor;
  control->cycle_end = (uint32_t)run_end;
  results[0].state = 4; results[0].cycle_start = (uint32_t)run_start;
  results[0].cycle_end = (uint32_t)run_end; results[0].transfers = shared_job.transfer_count;
  results[0].input_words = shared_job.input_words; results[0].output_words = shared_job.output_words;
  results[0].engine_cycles = shared_job.engine_cycles;
  results[0].work_low = shared_job.engine_work_low; results[0].work_high = shared_job.engine_work_high;
  control->state = 4; fence(); REG(PA_M5_CONSOLE, 8) = 1;
}

void m5_memory_main(uint32_t hart) {
  if (hart == 1) {
    results[1].state = 1;
    pa_m5_hw_service_hart1((pa_m5_hw_shared *)&shared_job);
  } else {
    run_hart0();
  }
  for (;;) __asm__ volatile("wfi");
}

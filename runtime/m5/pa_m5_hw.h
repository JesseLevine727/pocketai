#ifndef PA_M5_HW_H
#define PA_M5_HW_H
#include "pa_m5_ops.h"

#define PA_M5_HW_SHARED_MAGIC UINT32_C(0x354a4248)

enum { PA_M5_HW_GEMM = 1, PA_M5_HW_SFPU = 2 };

typedef struct {
  volatile uint32_t magic;
  volatile uint32_t hart1_ready;
  volatile uint32_t request_sequence;
  volatile uint32_t completion_sequence;
  volatile int32_t status;
  uint32_t kind;
  uint32_t rows;
  uint32_t k;
  uint32_t n;
  uint32_t operation;
  uint32_t length;
  uint32_t shift;
  uint32_t multiplier;
  uint32_t source[3];
  uint32_t source_words[3];
  uint32_t destination;
  uint32_t destination_words;
  uint32_t deadline;
  volatile uint32_t transfer_count;
  volatile uint32_t input_words;
  volatile uint32_t output_words;
  volatile uint32_t engine_cycles;
  volatile uint32_t engine_work_low;
  volatile uint32_t engine_work_high;
} pa_m5_hw_shared;

typedef struct {
  pa_m5_hw_shared *shared;
  uint32_t deadline;
} pa_m5_hw_context;

void pa_m5_hw_prepare_hart0(pa_m5_hw_context *context,
                            pa_m5_hw_shared *shared, uint32_t deadline);
int pa_m5_hw_wait_hart1(pa_m5_hw_context *context);
void pa_m5_hw_service_hart1(pa_m5_hw_shared *shared);
void pa_m5_hw_backend_open(pa_m5_backend *backend, pa_m5_hw_context *context);

#endif

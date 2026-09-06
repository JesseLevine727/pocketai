#ifndef PA_M5_RUNTIME_H
#define PA_M5_RUNTIME_H
#include "pa_m5_ops.h"

enum {
  PA_M5_TRACE_EMBEDDING = 1,
  PA_M5_TRACE_LN1 = 2,
  PA_M5_TRACE_QKV = 3,
  PA_M5_TRACE_CONTEXT = 4,
  PA_M5_TRACE_RESIDUAL = 5,
  PA_M5_TRACE_LN2 = 6,
  PA_M5_TRACE_UP = 7,
  PA_M5_TRACE_GELU = 8,
  PA_M5_TRACE_OUTPUT = 9,
  PA_M5_TRACE_FINAL_NORM = 10,
  PA_M5_TRACE_LOGITS = 11
};

typedef int (*pa_m5_trace_fn)(void *context, uint32_t kind, uint32_t layer,
                              const int16_t *values, const uint32_t *exponents,
                              uint32_t rows, uint32_t columns,
                              const double *channel_scale);

typedef struct {
  pa_m5_model *model;
  pa_m5_backend backend;
  pa_m5_workspace *workspace;
  pa_m5_cache *cache;
  void *trace_context;
  pa_m5_trace_fn trace;
} pa_m5_runtime;

int pa_m5_forward_chunk(pa_m5_runtime *runtime, const uint32_t *tokens,
                        uint32_t rows, uint32_t past,
                        int16_t *logits, uint32_t *logits_exponent);
int pa_m5_prefill(pa_m5_runtime *runtime, const uint32_t *tokens,
                  uint32_t count, uint32_t past,
                  int16_t *logits, uint32_t *logits_exponent);
int pa_m5_generate(pa_m5_runtime *runtime, const uint32_t *prompt,
                   uint32_t prompt_count, uint32_t generation_count,
                   uint32_t *generated, int16_t *final_logits,
                   uint32_t *final_logits_exponent, uint32_t *cache_valid);
#endif

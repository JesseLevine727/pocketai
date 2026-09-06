#include "pa_m5_runtime.h"

static int valid_runtime(const pa_m5_runtime *runtime) {
  return runtime && runtime->model && runtime->workspace && runtime->cache &&
         runtime->backend.gemm_tile && runtime->backend.sfpu;
}

static int emit_trace(pa_m5_runtime *runtime, uint32_t kind, uint32_t layer,
                      const int16_t *values, const uint32_t *exponents,
                      uint32_t rows, uint32_t columns,
                      const double *channel_scale) {
  return runtime->trace ? runtime->trace(runtime->trace_context, kind, layer,
                                         values, exponents, rows, columns,
                                         channel_scale) : 0;
}

int pa_m5_forward_chunk(pa_m5_runtime *runtime, const uint32_t *tokens,
                        uint32_t rows, uint32_t past,
                        int16_t *logits, uint32_t *logits_exponent) {
  if (!valid_runtime(runtime) || !tokens || !logits || !logits_exponent ||
      !rows || rows > 16 || past + rows > 1024) return -1;
  for (uint32_t row = 0; row < rows; ++row) if (tokens[row] >= 50257) return -1;
  pa_m5_workspace *work = runtime->workspace;
  uint32_t mark = work->used;
  int16_t *x0 = pa_m5_workspace_allocate(work, rows*768*2, 64);
  int16_t *x1 = pa_m5_workspace_allocate(work, rows*768*2, 64);
  int16_t *temporary0 = pa_m5_workspace_allocate(work, rows*768*2, 64);
  int16_t *temporary1 = pa_m5_workspace_allocate(work, rows*768*2, 64);
  int16_t *qkv = pa_m5_workspace_allocate(work, rows*2304*2, 64);
  int16_t *wide0 = pa_m5_workspace_allocate(work, rows*3072*2, 64);
  int16_t *wide1 = pa_m5_workspace_allocate(work, rows*3072*2, 64);
  uint32_t *exponent0 = pa_m5_workspace_allocate(work, rows*4, 64);
  uint32_t *exponent1 = pa_m5_workspace_allocate(work, rows*4, 64);
  uint32_t *temporary_exponent = pa_m5_workspace_allocate(work, rows*4, 64);
  uint32_t *zero_exponent = pa_m5_workspace_allocate(work, rows*4, 64);
  if (!x0 || !x1 || !temporary0 || !temporary1 || !qkv || !wide0 || !wide1 ||
      !exponent0 || !exponent1 || !temporary_exponent || !zero_exponent) {
    pa_m5_workspace_rewind(work, mark); return -2;
  }
  for (uint32_t row = 0; row < rows; ++row) {
    exponent0[row] = 0;
    zero_exponent[row] = 0;
    const int16_t *embedding = runtime->model->embedding + (uint64_t)tokens[row]*768;
    const int16_t *position = runtime->model->position + (uint64_t)(past+row)*768;
    for (uint32_t i = 0; i < 768; ++i)
      x0[row*768+i] = pa_m5_sat_i16((int32_t)embedding[i] + position[i]);
  }
  if (emit_trace(runtime, PA_M5_TRACE_EMBEDDING, 0, x0, zero_exponent,
                 rows, 768, 0)) {
    pa_m5_workspace_rewind(work, mark); return -3;
  }
  int16_t *x = x0, *next = x1;
  uint32_t *x_exponent = exponent0, *next_exponent = exponent1;
  for (uint32_t layer = 0; layer < 12; ++layer) {
    pa_m5_layer *parameters = &runtime->model->layers[layer];
    uint32_t stage = 1;
    int status = pa_m5_apply_norm(&runtime->backend, work, &parameters->norm1,
                                  x, x_exponent, rows, 768, temporary0);
    if (!status) { stage = 2; status = emit_trace(runtime, PA_M5_TRACE_LN1, layer, temporary0,
                                     zero_exponent, rows, 768,
                                     parameters->attention_qkv.smooth); }
    if (!status) { stage = 3; status = pa_m5_project(&runtime->backend, work, &parameters->attention_qkv,
                                        temporary0, zero_exponent, rows, 0, 0, 0,
                                        qkv, temporary_exponent); }
    if (!status) { stage = 4; status = emit_trace(runtime, PA_M5_TRACE_QKV, layer, qkv,
                                     zero_exponent, rows, 2304, 0); }
    if (!status) { stage = 5; status = pa_m5_attention(&runtime->backend, work, runtime->cache,
                                          layer, qkv, rows, past, temporary0); }
    if (!status) { stage = 6; status = emit_trace(runtime, PA_M5_TRACE_CONTEXT, layer, temporary0,
                                     zero_exponent, rows, 768, 0); }
    if (!status) { stage = 7; status = pa_m5_smooth(&runtime->backend, work, temporary0, rows, 768,
                                       parameters->attention_projection.smooth,
                                       temporary1, temporary_exponent); }
    if (!status) { stage = 8; status = pa_m5_project(&runtime->backend, work, &parameters->attention_projection,
                                        temporary1, temporary_exponent, rows, 1,
                                        x, x_exponent, next, next_exponent); }
    if (!status) { stage = 9; status = emit_trace(runtime, PA_M5_TRACE_RESIDUAL, layer, next,
                                     next_exponent, rows, 768, 0); }
    if (!status) { stage = 10; status = pa_m5_apply_norm(&runtime->backend, work, &parameters->norm2,
                                           next, next_exponent, rows, 768, temporary0); }
    if (!status) { stage = 11; status = emit_trace(runtime, PA_M5_TRACE_LN2, layer, temporary0,
                                     zero_exponent, rows, 768,
                                     parameters->mlp_up.smooth); }
    if (!status) { stage = 12; status = pa_m5_project(&runtime->backend, work, &parameters->mlp_up,
                                        temporary0, zero_exponent, rows, 0, 0, 0,
                                        wide0, temporary_exponent); }
    if (!status) { stage = 13; status = emit_trace(runtime, PA_M5_TRACE_UP, layer, wide0,
                                     zero_exponent, rows, 3072, 0); }
    if (!status) { stage = 14; status = pa_m5_gelu(&runtime->backend, work, wide0, rows*3072, wide1); }
    if (!status) { stage = 15; status = emit_trace(runtime, PA_M5_TRACE_GELU, layer, wide1,
                                     zero_exponent, rows, 3072, 0); }
    if (!status) { stage = 16; status = pa_m5_smooth(&runtime->backend, work, wide1, rows, 3072,
                                       parameters->mlp_down.smooth, wide0, temporary_exponent);
    }
    if (!status) { stage = 17; status = pa_m5_project(&runtime->backend, work, &parameters->mlp_down,
                                        wide0, temporary_exponent, rows, 1,
                                        next, next_exponent, x, x_exponent); }
    if (!status) { stage = 18; status = emit_trace(runtime, PA_M5_TRACE_OUTPUT, layer, x,
                                     x_exponent, rows, 768, 0); }
    if (status) {
      uint32_t detail = status < 0 ? (uint32_t)(-status) : (uint32_t)status;
      pa_m5_workspace_rewind(work, mark);
      return -(int)(1000 + layer*100 + stage*10 + detail);
    }
    // Down lands in the original x/x_exponent buffers; these remain current.
  }
  int status = pa_m5_apply_norm(&runtime->backend, work, &runtime->model->final_norm,
                                x, x_exponent, rows, 768, temporary0);
  if (!status) status = emit_trace(runtime, PA_M5_TRACE_FINAL_NORM, 0, temporary0,
                                   zero_exponent, rows, 768,
                                   runtime->model->lm_head.smooth);
  if (!status) status = pa_m5_project(&runtime->backend, work, &runtime->model->lm_head,
                                      temporary0+(rows-1)*768, zero_exponent, 1, 1, 0, 0,
                                      logits, logits_exponent);
  if (!status) status = emit_trace(runtime, PA_M5_TRACE_LOGITS, 0, logits,
                                   logits_exponent, 1, 50257, 0);
  pa_m5_workspace_rewind(work, mark);
  return status ? -30 : 0;
}

int pa_m5_prefill(pa_m5_runtime *runtime, const uint32_t *tokens,
                  uint32_t count, uint32_t past,
                  int16_t *logits, uint32_t *logits_exponent) {
  if (!valid_runtime(runtime) || !tokens || !count || past+count > 1024) return -1;
  uint32_t offset = 0;
  while (offset < count) {
    uint32_t rows = count-offset < 16 ? count-offset : 16;
    int status = pa_m5_forward_chunk(runtime, tokens+offset, rows, past+offset,
                                     logits, logits_exponent);
    if (status) return status;
    offset += rows;
  }
  return 0;
}

int pa_m5_generate(pa_m5_runtime *runtime, const uint32_t *prompt,
                   uint32_t prompt_count, uint32_t generation_count,
                   uint32_t *generated, int16_t *final_logits,
                   uint32_t *final_logits_exponent, uint32_t *cache_valid) {
  if (!valid_runtime(runtime) || !prompt || !generated || !final_logits ||
      !final_logits_exponent || !cache_valid || !prompt_count || !generation_count ||
      prompt_count+generation_count > 1024) return -1;
  uint32_t committed = *cache_valid;
  if (committed != 0) return -1;
  int status = pa_m5_prefill(runtime, prompt, prompt_count, 0,
                            final_logits, final_logits_exponent);
  if (status) return status;
  committed = prompt_count; *cache_valid = committed;
  for (uint32_t step = 0; step < generation_count; ++step) {
    uint32_t selected = 0;
    for (uint32_t token = 1; token < 50257; ++token)
      if (final_logits[token] > final_logits[selected]) selected = token;
    generated[step] = selected;
    if (step+1 < generation_count) {
      status = pa_m5_forward_chunk(runtime, &generated[step], 1, committed,
                                   final_logits, final_logits_exponent);
      if (status) return status;
      ++committed; *cache_valid = committed;
    }
  }
  return 0;
}

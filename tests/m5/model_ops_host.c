#include "pa_m5_runtime.h"
#include <stdint.h>

static int host_gemm(void *context, uint32_t rows, uint32_t k, uint32_t n,
                     const int8_t *a, const int8_t *tile, int32_t *output) {
  (void)context;
  if (!rows || rows > 16 || !k || k > 3072 || !n || n > 16) return -1;
  for (uint32_t row = 0; row < rows; ++row) for (uint32_t column = 0; column < 16; ++column) {
    int32_t sum = 0;
    for (uint32_t inner = 0; inner < k; ++inner)
      sum += (int32_t)a[row*k+inner] * (int32_t)tile[inner*16+column];
    output[row*16+column] = sum;
  }
  return 0;
}
extern int pa_m4_sfpu(int op, int length, int shift, uint32_t multiplier,
                      const int32_t *input, int32_t *output,
                      const int16_t *gelu_table, const uint32_t *exp_table);
static int32_t packet[3*3072];
static const int16_t *host_gelu_table;
static const uint32_t *host_exp_table;
void pa_m5_host_tables(const int16_t *gelu, const uint32_t *exp) {
  host_gelu_table = gelu; host_exp_table = exp;
}
static int host_sfpu(void *context, uint32_t op, uint32_t length, uint32_t shift,
                     uint32_t multiplier, const int32_t *plane0,
                     const int32_t *plane1, const int32_t *plane2, int32_t *output) {
  (void)context;
  for (uint32_t i = 0; i < length; ++i) packet[i] = plane0[i];
  if (op == PA_M5_SFPU_ADD || op == PA_M5_SFPU_LAYERNORM || op == PA_M5_SFPU_AFFINE ||
      op == PA_M5_SFPU_AFFINE_GELU)
    for (uint32_t i = 0; i < length; ++i) packet[length+i] = plane1[i];
  if (op == PA_M5_SFPU_LAYERNORM || op == PA_M5_SFPU_AFFINE || op == PA_M5_SFPU_AFFINE_GELU)
    for (uint32_t i = 0; i < length; ++i) packet[2*length+i] = plane2[i];
  if (!host_gelu_table || !host_exp_table) return -1;
  return pa_m4_sfpu((int)op, (int)length, (int)shift, multiplier, packet, output,
                    host_gelu_table, host_exp_table);
}
static pa_m5_linear *select_linear(pa_m5_model *model, uint32_t selector) {
  if (selector == 0) return &model->layers[0].attention_qkv;
  if (selector == 1) return &model->layers[0].attention_projection;
  if (selector == 2) return &model->layers[0].mlp_up;
  if (selector == 3) return &model->layers[0].mlp_down;
  if (selector == 4) return &model->lm_head;
  return 0;
}
int pa_m5_host_project(const void *arena, void *work, uint32_t work_bytes,
                       uint32_t selector, const int16_t *input,
                       const uint32_t *input_exponents, uint32_t rows, int scaled,
                       const int16_t *residual, const uint32_t *residual_exponents,
                       int16_t *output, uint32_t *output_exponents,
                       uint32_t *high_water) {
  pa_m5_model model; pa_m5_workspace workspace;
  pa_m5_backend backend = {0, host_gemm, host_sfpu};
  if (pa_m5_model_open(&model, arena, PA_M5_ARENA_BYTES)) return -10;
  pa_m5_linear *linear = select_linear(&model, selector);
  if (!linear) return -11;
  pa_m5_workspace_open(&workspace, work, work_bytes);
  int status = pa_m5_project(&backend, &workspace, linear, input, input_exponents,
                             rows, scaled, residual, residual_exponents,
                             output, output_exponents);
  if (high_water) *high_water = workspace.high_water;
  return status;
}
int pa_m5_host_smooth(const void *arena, void *work, uint32_t work_bytes,
                      uint32_t selector, const int16_t *input, uint32_t rows,
                      int16_t *output, uint32_t *exponents, uint32_t *high_water) {
  pa_m5_model model; pa_m5_workspace workspace;
  pa_m5_backend backend = {0, host_gemm, host_sfpu};
  if (pa_m5_model_open(&model, arena, PA_M5_ARENA_BYTES)) return -10;
  pa_m5_linear *linear = select_linear(&model, selector);
  if (!linear) return -11;
  pa_m5_workspace_open(&workspace, work, work_bytes);
  int status = pa_m5_smooth(&backend, &workspace, input, rows, linear->k,
                            linear->smooth, output, exponents);
  if (high_water) *high_water = workspace.high_water;
  return status;
}
int pa_m5_host_norm(const void *arena, void *work, uint32_t work_bytes,
                    uint32_t selector, const int16_t *input,
                    const uint32_t *exponents, uint32_t rows,
                    int16_t *output, uint32_t *high_water) {
  pa_m5_model model; pa_m5_workspace workspace;
  pa_m5_backend backend = {0, host_gemm, host_sfpu};
  if (pa_m5_model_open(&model, arena, PA_M5_ARENA_BYTES)) return -10;
  pa_m5_norm *norm = selector == 0 ? &model.layers[0].norm1 :
                      selector == 1 ? &model.layers[0].norm2 :
                      selector == 2 ? &model.final_norm : 0;
  if (!norm) return -11;
  pa_m5_workspace_open(&workspace, work, work_bytes);
  int status = pa_m5_apply_norm(&backend, &workspace, norm, input, exponents, rows, 768, output);
  if (high_water) *high_water = workspace.high_water;
  return status;
}
int pa_m5_host_gelu(void *work, uint32_t work_bytes, const int16_t *input,
                    uint32_t count, int16_t *output, uint32_t *high_water) {
  pa_m5_workspace workspace; pa_m5_backend backend = {0, host_gemm, host_sfpu};
  pa_m5_workspace_open(&workspace, work, work_bytes);
  int status = pa_m5_gelu(&backend, &workspace, input, count, output);
  if (high_water) *high_water = workspace.high_water;
  return status;
}
int pa_m5_host_attention(void *work, uint32_t work_bytes,
                         int16_t *keys, int16_t *values, int8_t *keys_i8,
                         double *key_units, uint32_t layer, const int16_t *qkv,
                         uint32_t rows, uint32_t past, int16_t *context,
                         uint32_t *high_water) {
  pa_m5_workspace workspace; pa_m5_backend backend = {0, host_gemm, host_sfpu};
  pa_m5_cache cache = {keys, values, keys_i8, key_units};
  pa_m5_workspace_open(&workspace, work, work_bytes);
  int status = pa_m5_attention(&backend, &workspace, &cache, layer, qkv, rows, past, context);
  if (high_water) *high_water = workspace.high_water;
  return status;
}
int pa_m5_host_forward(const void *arena, void *work, uint32_t work_bytes,
                       int16_t *keys, int16_t *values, int8_t *keys_i8,
                       double *key_units, const uint32_t *tokens,
                       uint32_t rows, uint32_t past, int16_t *logits,
                       uint32_t *logits_exponent, uint32_t *high_water) {
  pa_m5_model model; pa_m5_workspace workspace;
  pa_m5_cache cache = {keys, values, keys_i8, key_units};
  pa_m5_runtime runtime;
  if (pa_m5_model_open(&model, arena, PA_M5_ARENA_BYTES)) return -10;
  pa_m5_workspace_open(&workspace, work, work_bytes);
  runtime.model = &model; runtime.workspace = &workspace; runtime.cache = &cache;
  runtime.backend.context = 0; runtime.backend.gemm_tile = host_gemm; runtime.backend.sfpu = host_sfpu;
  runtime.trace_context = 0; runtime.trace = 0;
  int status = pa_m5_forward_chunk(&runtime, tokens, rows, past, logits, logits_exponent);
  if (high_water) *high_water = workspace.high_water;
  return status;
}

int pa_m5_host_forward_trace(const void *arena, void *work, uint32_t work_bytes,
                             int16_t *keys, int16_t *values, int8_t *keys_i8,
                             double *key_units, const uint32_t *tokens,
                             uint32_t rows, uint32_t past, int16_t *logits,
                             uint32_t *logits_exponent, uint32_t *high_water,
                             pa_m5_trace_fn trace, void *trace_context) {
  pa_m5_model model; pa_m5_workspace workspace;
  pa_m5_cache cache = {keys, values, keys_i8, key_units};
  pa_m5_runtime runtime;
  if (pa_m5_model_open(&model, arena, PA_M5_ARENA_BYTES)) return -10;
  pa_m5_workspace_open(&workspace, work, work_bytes);
  runtime.model = &model; runtime.workspace = &workspace; runtime.cache = &cache;
  runtime.backend.context = 0; runtime.backend.gemm_tile = host_gemm;
  runtime.backend.sfpu = host_sfpu;
  runtime.trace_context = trace_context; runtime.trace = trace;
  int status = pa_m5_forward_chunk(&runtime, tokens, rows, past,
                                   logits, logits_exponent);
  if (high_water) *high_water = workspace.high_water;
  return status;
}

int pa_m5_host_generate(const void *arena, void *work, uint32_t work_bytes,
                        int16_t *keys, int16_t *values, int8_t *keys_i8,
                        double *key_units, const uint32_t *prompt,
                        uint32_t prompt_count, uint32_t generation_count,
                        uint32_t *generated, int16_t *final_logits,
                        uint32_t *final_logits_exponent, uint32_t *cache_valid,
                        uint32_t *high_water) {
  pa_m5_model model; pa_m5_workspace workspace;
  pa_m5_cache cache = {keys, values, keys_i8, key_units};
  pa_m5_runtime runtime;
  if (pa_m5_model_open(&model, arena, PA_M5_ARENA_BYTES)) return -10;
  pa_m5_workspace_open(&workspace, work, work_bytes);
  runtime.model = &model; runtime.workspace = &workspace; runtime.cache = &cache;
  runtime.backend.context = 0; runtime.backend.gemm_tile = host_gemm;
  runtime.backend.sfpu = host_sfpu;
  runtime.trace_context = 0; runtime.trace = 0;
  int status = pa_m5_generate(&runtime, prompt, prompt_count, generation_count,
                              generated, final_logits, final_logits_exponent,
                              cache_valid);
  if (high_water) *high_water = workspace.high_water;
  return status;
}

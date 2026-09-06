#ifndef PA_M5_OPS_H
#define PA_M5_OPS_H
#include "pa_m5_model.h"

enum { PA_M5_SFPU_GELU=1, PA_M5_SFPU_LAYERNORM=2, PA_M5_SFPU_SOFTMAX=3,
       PA_M5_SFPU_AFFINE=4, PA_M5_SFPU_REQUANT8=5,
       PA_M5_SFPU_AFFINE_GELU=6, PA_M5_SFPU_ADD=7 };
typedef struct {
  void *context;
  int (*gemm_tile)(void *context, uint32_t rows, uint32_t k, uint32_t n,
                   const int8_t *a, const int8_t *tile, int32_t *output16);
  int (*sfpu)(void *context, uint32_t op, uint32_t length, uint32_t shift,
              uint32_t multiplier, const int32_t *plane0,
              const int32_t *plane1, const int32_t *plane2, int32_t *output);
} pa_m5_backend;
typedef struct {
  int16_t *keys;
  int16_t *values;
  int8_t *keys_i8;
  double *key_units;
} pa_m5_cache;

int pa_m5_dynamic_quantize(const int16_t *input, uint32_t rows, uint32_t columns,
                           int8_t *output, double *units);
int pa_m5_smooth(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                 const int16_t *input, uint32_t rows, uint32_t columns,
                 const double *smoothing, int16_t *output, uint32_t *exponents);
int pa_m5_apply_norm(const pa_m5_backend *backend, pa_m5_workspace *workspace,
               const pa_m5_norm *norm, const int16_t *input,
               const uint32_t *exponents, uint32_t rows, uint32_t columns,
               int16_t *output);
int pa_m5_gelu(const pa_m5_backend *backend, pa_m5_workspace *workspace,
               const int16_t *input, uint32_t count, int16_t *output);
void pa_m5_cache_open(pa_m5_cache *cache, void *arena_base);
int pa_m5_attention(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                    pa_m5_cache *cache, uint32_t layer, const int16_t *qkv,
                    uint32_t rows, uint32_t past, int16_t *context);
int pa_m5_project(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                  const pa_m5_linear *linear, const int16_t *input,
                  const uint32_t *input_exponents, uint32_t rows,
                  int scaled, const int16_t *residual,
                  const uint32_t *residual_exponents,
                  int16_t *output, uint32_t *output_exponents);
#endif

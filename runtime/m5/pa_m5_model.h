#ifndef PA_M5_MODEL_H
#define PA_M5_MODEL_H
#include "pa_m5_numerics.h"

typedef struct {
  const int8_t *tiles;
  const double *scale;
  const double *bias;
  const double *smooth;
  uint32_t k, n;
} pa_m5_linear;

typedef struct { const double *gain, *bias; } pa_m5_norm;
typedef struct {
  pa_m5_linear attention_qkv, attention_projection, mlp_up, mlp_down;
  pa_m5_norm norm1, norm2;
} pa_m5_layer;

typedef struct {
  pa_m5_arena arena;
  const int16_t *embedding;
  const int16_t *position;
  pa_m5_layer layers[12];
  pa_m5_norm final_norm;
  pa_m5_linear lm_head;
} pa_m5_model;

typedef struct {
  uint8_t *base;
  uint32_t capacity, used, high_water;
} pa_m5_workspace;

int pa_m5_model_open(pa_m5_model *model, const void *arena, uint32_t arena_bytes);
void pa_m5_workspace_open(pa_m5_workspace *workspace, void *base, uint32_t capacity);
void pa_m5_workspace_rewind(pa_m5_workspace *workspace, uint32_t mark);
void *pa_m5_workspace_allocate(pa_m5_workspace *workspace, uint32_t bytes, uint32_t alignment);
#endif

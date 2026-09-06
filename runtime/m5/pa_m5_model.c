#include "pa_m5_model.h"

static void bind_linear(pa_m5_model *model, pa_m5_linear *linear,
                        uint32_t id, uint32_t k, uint32_t n) {
  linear->tiles = pa_m5_arena_array(&model->arena, id, 0);
  linear->scale = pa_m5_arena_array(&model->arena, id + 1, 0);
  linear->bias = pa_m5_arena_array(&model->arena, id + 2, 0);
  linear->smooth = pa_m5_arena_array(&model->arena, id + 3, 0);
  linear->k = k; linear->n = n;
}
static void bind_norm(pa_m5_model *model, pa_m5_norm *norm, uint32_t id) {
  norm->gain = pa_m5_arena_array(&model->arena, id, 0);
  norm->bias = pa_m5_arena_array(&model->arena, id + 1, 0);
}

int pa_m5_model_open(pa_m5_model *model, const void *arena, uint32_t arena_bytes) {
  if (!model || pa_m5_arena_open(&model->arena, arena, arena_bytes)) return -1;
  model->embedding = pa_m5_arena_array(&model->arena, 0, 0);
  model->position = pa_m5_arena_array(&model->arena, 1, 0);
  for (uint32_t layer = 0; layer < 12; ++layer) {
    uint32_t id = 2 + layer * 20;
    bind_linear(model, &model->layers[layer].attention_qkv, id, 768, 2304);
    bind_linear(model, &model->layers[layer].attention_projection, id + 4, 768, 768);
    bind_linear(model, &model->layers[layer].mlp_up, id + 8, 768, 3072);
    bind_linear(model, &model->layers[layer].mlp_down, id + 12, 3072, 768);
    bind_norm(model, &model->layers[layer].norm1, id + 16);
    bind_norm(model, &model->layers[layer].norm2, id + 18);
  }
  bind_norm(model, &model->final_norm, 242);
  bind_linear(model, &model->lm_head, 244, 768, 50257);
  return 0;
}

void pa_m5_workspace_open(pa_m5_workspace *workspace, void *base, uint32_t capacity) {
  if (!workspace) return;
  workspace->base = base; workspace->capacity = capacity;
  workspace->used = 0; workspace->high_water = 0;
}
void pa_m5_workspace_rewind(pa_m5_workspace *workspace, uint32_t mark) {
  if (workspace && mark <= workspace->used) workspace->used = mark;
}
void *pa_m5_workspace_allocate(pa_m5_workspace *workspace, uint32_t bytes, uint32_t alignment) {
  if (!workspace || !workspace->base || !bytes || !alignment || (alignment & (alignment - 1))) return 0;
  uint64_t start = ((uint64_t)workspace->used + alignment - 1) & ~((uint64_t)alignment - 1);
  uint64_t end = start + bytes;
  if (end > workspace->capacity) return 0;
  workspace->used = (uint32_t)end;
  if (workspace->used > workspace->high_water) workspace->high_water = workspace->used;
  return workspace->base + start;
}

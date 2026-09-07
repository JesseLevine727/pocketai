/* Include the pinned actual retained definition of affine_row, not a rewritten
 * oracle. The fake device also checks that both paths emit identical planes. */
#include "../../build/m5_fast_runtime_requant_v1/generated/ops.c"
#include "../../runtime/m5_iterate/attention_prepared.c.inc"
static int probe_sfpu(void *opaque, uint32_t operation, uint32_t length, uint32_t shift,
                       uint32_t multiplier, const int32_t *p0, const int32_t *p1,
                       const int32_t *p2, int32_t *output) {
  uint32_t *state = opaque;
  ++state[0];
  state[1] = state[1]*33u + operation + length + shift + multiplier;
  for (uint32_t i = 0; i < length; ++i) {
    state[1] = state[1]*33u + (uint32_t)p0[i];
    state[1] = state[1]*33u + (uint32_t)p1[i];
    state[1] = state[1]*33u + (uint32_t)p2[i];
    int64_t value = pa_m5_rne_i64((int64_t)p0[i]*p1[i], UINT64_C(1)<<shift) + p2[i];
    output[i] = value < INT32_MIN ? INT32_MIN : value > INT32_MAX ? INT32_MAX : (int32_t)value;
  }
  return state[2] ? -1 : 0;
}
int pa_iter_attention_probe(int candidate, void *work, uint32_t capacity,
                             const int32_t *input, const double *scales, uint32_t count,
                             int64_t maximum, int16_t *output, uint32_t *state) {
  pa_m5_workspace workspace;
  pa_m5_workspace_open(&workspace, work, capacity);
  workspace.used = 17;
  pa_m5_backend backend = {state, 0, probe_sfpu};
  uint32_t *multipliers = pa_m5_workspace_allocate(&workspace, count*4, 64), shift = 0;
  if (!multipliers) return -99;
  if (pa_m5_affine_metadata(scales, count, multipliers, &shift)) return -98;
  int status;
  if (candidate) {
    status = pa_iter_attention_affine(&backend, &workspace, input, multipliers, shift,
                                      maximum, count, output);
    workspace.used = (uint32_t)((uint8_t *)multipliers-workspace.base);
  } else {
    double bias[1024];
    for (uint32_t i = 0; i < count; ++i) bias[i] = -(double)maximum;
    workspace.used = (uint32_t)((uint8_t *)multipliers-workspace.base);
    status = affine_row(&backend, &workspace, input, scales, bias, count,
                         PA_M5_SFPU_AFFINE, output);
  }
  state[3] = workspace.used; state[4] = workspace.high_water;
  return status;
}

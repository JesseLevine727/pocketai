#include "../../build/m5_scalar_affine_v1/generated/ops.c"
#include "../../runtime/m5_scalar/affine_round.h"
#include "../../runtime/m5_search/project_affine.c.inc"
static int probe_sfpu(void *opaque, uint32_t operation, uint32_t length, uint32_t shift,
                       uint32_t multiplier, const int32_t *p0, const int32_t *p1,
                       const int32_t *p2, int32_t *output) {
  uint32_t *state = opaque;
  ++state[0]; state[1] = state[1]*33u + operation + length + shift + multiplier;
  for (uint32_t i = 0; i < length; ++i) {
    state[1] = state[1]*33u + (uint32_t)p0[i];
    state[1] = state[1]*33u + (uint32_t)p1[i];
    state[1] = state[1]*33u + (uint32_t)p2[i];
    int64_t value = pa_m5_rne_i64((int64_t)p0[i]*p1[i], UINT64_C(1)<<shift) + p2[i];
    output[i] = value < INT32_MIN ? INT32_MIN : value > INT32_MAX ? INT32_MAX : (int32_t)value;
  }
  return state[2] == state[0] ? -1 : 0;
}
int pa_search_fusion_probe(int candidate, void *work, uint32_t capacity,
                            const int32_t *input, double *scales, const double *bias,
                            double *bias_scratch, uint32_t count, int power_shift,
                            int16_t *output, uint32_t *state) {
  pa_m5_workspace workspace; pa_m5_workspace_open(&workspace, work, capacity);
  workspace.used = 17;
  pa_m5_backend backend = {state, 0, probe_sfpu};
  int status;
  if (candidate) status = pa_search_project_affine(&backend, &workspace, input,
                         scales, bias, bias_scratch, count, power_shift, output);
  else {
    for (uint32_t i = 0; i < count; ++i) {
      scales[i] = pa_fast_scale_power2(scales[i], power_shift);
      bias_scratch[i] = pa_fast_scale_power2(bias[i], power_shift);
    }
    status = affine_row(&backend, &workspace, input, scales, bias_scratch,
                         count, PA_M5_SFPU_AFFINE, output);
  }
  state[3] = workspace.used; state[4] = workspace.high_water;
  return status;
}

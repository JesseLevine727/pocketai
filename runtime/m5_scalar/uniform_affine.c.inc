/* Common scale with already-integer bias: prepare ONE exact multiplier, then
 * fill consumer planes. Keep original allocation order, backend chunking,
 * error codes, partial output behavior and workspace rewind boundary. */
static int pa_scalar_uniform_affine(const pa_m5_backend *backend,
                                    pa_m5_workspace *workspace,
                                    const int32_t *input, double scale,
                                    const int32_t *integer_bias, uint32_t count,
                                    int16_t *output) {
  uint32_t mark = workspace->used;
  uint32_t *multipliers = pa_m5_workspace_allocate(workspace, count*4, 64);
  int32_t *bias = pa_m5_workspace_allocate(workspace, count*4, 64);
  int32_t *result = pa_m5_workspace_allocate(workspace, count*4, 64);
  if (!multipliers || !bias || !result) { pa_m5_workspace_rewind(workspace, mark); return -1; }
  uint32_t multiplier, shift;
  if (pa_m5_affine_metadata(&scale, 1, &multiplier, &shift)) {
    pa_m5_workspace_rewind(workspace, mark); return -2;
  }
  for (uint32_t i = 0; i < count; ++i) {
    multipliers[i] = multiplier; bias[i] = integer_bias ? integer_bias[i] : 0;
  }
  for (uint32_t offset = 0; offset < count; offset += 3072) {
    uint32_t length = count-offset < 3072 ? count-offset : 3072;
    if (backend->sfpu(backend->context, PA_M5_SFPU_AFFINE, length, shift, 0,
                      input+offset, (const int32_t *)(multipliers+offset),
                      bias+offset, result+offset)) {
      pa_m5_workspace_rewind(workspace, mark); return -3;
    }
  }
  for (uint32_t i = 0; i < count; ++i) {
    if (result[i] < -32768 || result[i] > 32767) {
      pa_m5_workspace_rewind(workspace, mark); return -3;
    }
    output[i] = (int16_t)result[i];
  }
  pa_m5_workspace_rewind(workspace, mark); return 0;
}

/* Consume the already validated score metadata, preserving the original
 * SFPU affine rounding and saturation. Both temporary planes remain DDR. */
static int pa_iter_attention_affine(const pa_m5_backend *backend,
                                   pa_m5_workspace *workspace,
                                   const int32_t *input, const uint32_t *multipliers,
                                   uint32_t shift, int64_t maximum, uint32_t count,
                                   int16_t *output) {
  uint32_t mark = workspace->used;
  int32_t *bias = pa_m5_workspace_allocate(workspace, count*4, 64);
  int32_t *result = pa_m5_workspace_allocate(workspace, count*4, 64);
  if (!bias || !result) { pa_m5_workspace_rewind(workspace, mark); return -1; }
  /* Exactly the integer produced by original RNE(-(double)maximum). */
  int64_t offset = -maximum;
  if (offset < INT32_MIN || offset > INT32_MAX) {
    pa_m5_workspace_rewind(workspace, mark); return -4;
  }
  for (uint32_t i = 0; i < count; ++i) bias[i] = (int32_t)offset;
  int status = 0;
  if (backend->sfpu(backend->context, PA_M5_SFPU_AFFINE, count, shift, 0,
                    input, (const int32_t *)multipliers, bias, result)) status = -3;
  if (!status) for (uint32_t i = 0; i < count; ++i) {
    if (result[i] < -32768 || result[i] > 32767) { status = -3; break; }
    output[i] = (int16_t)result[i];
  }
  pa_m5_workspace_rewind(workspace, mark);
  return status;
}

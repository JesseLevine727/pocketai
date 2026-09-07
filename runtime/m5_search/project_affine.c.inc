/* Fuse final channel scaling, bias conversion and affine-plane preparation.
 * Scales are the original ordered unit*weight*input-unit values. Their global
 * exponent has already been selected; this never uses tile-local exponents.
 * Keep the original allocations and fallback for non-normal/invalid inputs. */
static int pa_search_project_affine(const pa_m5_backend *backend,
                                    pa_m5_workspace *workspace,
                                    const int32_t *input, double *scales,
                                    const double *raw_bias, double *bias_scratch,
                                    uint32_t count, int power_shift,
                                    int16_t *output) {
  uint32_t mark = workspace->used;
  uint32_t *multipliers = pa_m5_workspace_allocate(workspace, count*4, 64);
  int32_t *bias = pa_m5_workspace_allocate(workspace, count*4, 64);
  int32_t *result = pa_m5_workspace_allocate(workspace, count*4, 64);
  if (!multipliers || !bias || !result) { pa_m5_workspace_rewind(workspace, mark); return -1; }
  if (!count) goto fallback;
  uint64_t maximum = 0;
  for (uint32_t i = 0; i < count; ++i) {
    union { double floating; uint64_t bits; } value = {.floating = scales[i]};
    int encoded = (int)((value.bits >> 52) & 2047u);
    if ((value.bits >> 63) || !encoded || encoded == 2047 ||
        encoded+power_shift <= 0 || encoded+power_shift >= 2047) goto fallback;
    if (value.bits > maximum) maximum = value.bits;
  }
  /* Proven normal-to-normal power-of-two scaling changes only exponent bits.
   * Unsigned modular addition also represents a negative exponent adjustment. */
  uint64_t adjustment = (uint64_t)(int64_t)power_shift << 52;
  maximum += adjustment;
  uint32_t shift = 31;
  while (shift && pa_scalar_rne_scaled32(maximum, shift) >= UINT32_C(0x80000000)) --shift;
  for (uint32_t i = 0; i < count; ++i) {
    union { double floating; uint64_t bits; } value = {.floating = scales[i]};
    uint32_t rounded = pa_scalar_rne_scaled32(value.bits+adjustment, shift);
    if (!rounded || rounded >= UINT32_C(0x80000000)) goto fallback;
    multipliers[i] = rounded;
    int64_t rounded_bias = pa_m5_rne_f64_signed(pa_fast_scale_power2(raw_bias[i], power_shift));
    if (rounded_bias < INT32_MIN || rounded_bias > INT32_MAX) goto fallback;
    bias[i] = (int32_t)rounded_bias;
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

fallback:
  /* No backend call/output occurred. Recreate the exact original finalization
   * and let its full generic metadata/error semantics decide the result. */
  for (uint32_t i = 0; i < count; ++i) {
    scales[i] = pa_fast_scale_power2(scales[i], power_shift);
    bias_scratch[i] = pa_fast_scale_power2(raw_bias[i], power_shift);
  }
  pa_m5_workspace_rewind(workspace, mark);
  return affine_row(backend, workspace, input, scales, bias_scratch, count,
                     PA_M5_SFPU_AFFINE, output);
}

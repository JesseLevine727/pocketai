// Isolated smoothing preparation reuse; all other operations are unchanged.
#define pa_m5_smooth pa_m5_baseline_smooth
#include "../m5/pa_m5_ops.c"
#undef pa_m5_smooth

int pa_m5_smooth(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                 const int16_t *input, uint32_t rows, uint32_t columns,
                 const double *smoothing, int16_t *output, uint32_t *exponents) {
  if (!backend || !backend->sfpu || !workspace || !input || !smoothing || !output ||
      !exponents || !rows || rows > 16 || !columns || columns > 3072) return -1;
  uint32_t mark = workspace->used;
  double *reciprocal = pa_m5_workspace_allocate(workspace, columns * 8, 64);
  double *scales = pa_m5_workspace_allocate(workspace, columns * 8, 64);
  double *zero_bias = pa_m5_workspace_allocate(workspace, columns * 8, 64);
  uint32_t *multipliers = pa_m5_workspace_allocate(workspace, columns * 4, 64);
  if (!reciprocal || !scales || !zero_bias || !multipliers) {
    pa_m5_workspace_rewind(workspace, mark); return -2;
  }
  for (uint32_t i = 0; i < columns; ++i) {
    reciprocal[i] = 1.0 / smoothing[i]; zero_bias[i] = 0.0;
  }
  uint32_t shift;
  if (pa_m5_affine_metadata(reciprocal, columns, multipliers, &shift)) {
    pa_m5_workspace_rewind(workspace, mark); return -3;
  }
  int any_overflow = 0;
  for (uint32_t row = 0; row < rows; ++row) {
    exponents[row] = 0;
    for (uint32_t i = 0; i < columns; ++i) {
      int64_t prospective = pa_m5_rne_i64((int64_t)input[row*columns+i] * multipliers[i],
                                         UINT64_C(1) << shift);
      if (prospective < -32768 || prospective > 32767) any_overflow = 1;
    }
  }
  for (uint32_t row = 0; row < rows; ++row) {
    if (any_overflow) {
      double maximum = 0.0;
      for (uint32_t i = 0; i < columns; ++i) {
        double logical = (double)input[row*columns+i] * reciprocal[i];
        if (logical < 0) logical = -logical;
        if (logical > maximum) maximum = logical;
      }
      exponents[row] = pa_m5_storage_exponent(maximum / 256.0);
      if (exponents[row] == UINT32_MAX) {
        pa_m5_workspace_rewind(workspace, mark); return -3;
      }
    }
    uint32_t row_mark = workspace->used;
    int32_t *expanded = pa_m5_workspace_allocate(workspace, columns * 4, 64);
    if (!expanded) { pa_m5_workspace_rewind(workspace, mark); return -2; }
    for (uint32_t i = 0; i < columns; ++i) expanded[i] = input[row*columns+i];
    int status;
    if (!exponents[row]) {
      // The overflow probe already produced the exact common multipliers.
      // No second metadata pass, float64 zero-bias conversion or divide by 1.
      int32_t *zero = pa_m5_workspace_allocate(workspace, columns * 4, 64);
      int32_t *result = pa_m5_workspace_allocate(workspace, columns * 4, 64);
      if (!zero || !result) { pa_m5_workspace_rewind(workspace, mark); return -2; }
      for (uint32_t i = 0; i < columns; ++i) zero[i] = 0;
      status = backend->sfpu(backend->context, PA_M5_SFPU_AFFINE, columns, shift, 0,
                            expanded, (const int32_t *)multipliers, zero, result);
      if (!status) for (uint32_t i = 0; i < columns; ++i) {
        if (result[i] < -32768 || result[i] > 32767) { status = -3; break; }
        output[row*columns+i] = (int16_t)result[i];
      }
      if (status) status = -3;
    } else {
      for (uint32_t i = 0; i < columns; ++i)
        scales[i] = reciprocal[i] / power2(exponents[row]);
      status = affine_row(backend, workspace, expanded, scales, zero_bias, columns,
                          PA_M5_SFPU_AFFINE, output + row*columns);
    }
    pa_m5_workspace_rewind(workspace, row_mark);
    if (status) { pa_m5_workspace_rewind(workspace, mark); return status; }
  }
  pa_m5_workspace_rewind(workspace, mark); return 0;
}

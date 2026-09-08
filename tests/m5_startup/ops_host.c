/* Native-only generic-shape seam. No board firmware includes this file. */
#include "pa_m5_ops.h"
#include "pa_m5_requant.h"
extern int pa_m4_sfpu(int, int, int, uint32_t, const int32_t *, int32_t *,
                       const int16_t *, const uint32_t *);
static int scalar(void *context, uint32_t op, uint32_t length, uint32_t shift,
                    uint32_t multiplier, const int32_t *a, const int32_t *b,
                    const int32_t *d, int32_t *output) {
  (void)context;
  if ((op != 4 && op != 5) || length > 3072) return -1;
  int32_t packet[3*3072]; const int16_t gelu[1] = {0}; const uint32_t exp[1] = {0};
  for (uint32_t i = 0; i < length; ++i) {
    packet[i] = a[i];
    if (op == 4) { packet[length+i] = b[i]; packet[2*length+i] = d[i]; }
  }
  return pa_m4_sfpu((int)op, (int)length, (int)shift, multiplier, packet, output, gelu, exp);
}
int pa_startup_smooth_generic(const int16_t *input, uint32_t rows, uint32_t columns,
    const double *smoothing, int16_t *output, uint32_t *exponents,
    void *work, uint32_t capacity, uint32_t *used) {
  pa_m5_workspace workspace; pa_m5_workspace_open(&workspace, work, capacity);
  pa_m5_backend backend = {0, 0, scalar};
  int status = pa_m5_smooth(&backend, &workspace, input, rows, columns,
                           smoothing, output, exponents);
  *used = workspace.used; return status;
}
int pa_startup_quant_generic(const int16_t *input, uint32_t rows, uint32_t columns,
    int8_t *output, double *units, void *work, uint32_t capacity, uint32_t *used) {
  pa_m5_workspace workspace; pa_m5_workspace_open(&workspace, work, capacity);
  pa_m5_backend backend = {0, 0, scalar};
  int status = pa_m5_requant_offload(&backend, &workspace, input, rows, columns, output, units);
  *used = workspace.used; return status;
}

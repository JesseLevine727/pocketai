#include "pa_m5_requant.h"
/* Candidate only: the complete conversion includes expansion and packing. */
int pa_m5_requant_offload(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                          const int16_t *input, uint32_t rows, uint32_t columns,
                          int8_t *output, double *units) {
  if (!backend || !backend->sfpu || !workspace || !input || !output || !units ||
      !rows || rows > 16 || !columns || columns > 3072) return -1;
  uint32_t mark = workspace->used;
  int32_t *expanded = pa_m5_workspace_allocate(workspace, columns*4, 64);
  int32_t *result = pa_m5_workspace_allocate(workspace, columns*4, 64);
  if (!expanded || !result) { pa_m5_workspace_rewind(workspace, mark); return -1; }
  int status = 0;
  for (uint32_t row = 0; row < rows; ++row) {
    uint32_t maximum = 0;
    for (uint32_t column = 0; column < columns; ++column) {
      int32_t value = input[row*columns+column];
      uint32_t magnitude = value < 0 ? (uint32_t)-value : (uint32_t)value;
      if (magnitude > maximum) maximum = magnitude;
      expanded[column] = value;
    }
    uint32_t multiplier = pa_m5_dynamic_multiplier(maximum);
    if (multiplier == UINT32_MAX) { status = -2; break; }
    units[row] = pa_m5_dynamic_unit(multiplier, 1.0/256.0);
    if (backend->sfpu(backend->context, PA_M5_SFPU_REQUANT8, columns, 24,
                      multiplier, expanded, 0, 0, result)) { status = -3; break; }
    for (uint32_t column = 0; column < columns; ++column) {
      if (result[column] < -128 || result[column] > 127) { status = -3; break; }
      output[row*columns+column] = (int8_t)result[column];
    }
    if (status) break;
  }
  pa_m5_workspace_rewind(workspace, mark); return status;
}

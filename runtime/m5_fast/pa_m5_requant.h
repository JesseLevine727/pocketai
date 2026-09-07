#ifndef PA_M5_REQUANT_H
#define PA_M5_REQUANT_H
#include "pa_m5_ops.h"
int pa_m5_requant_offload(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                          const int16_t *input, uint32_t rows, uint32_t columns,
                          int8_t *output, double *units);
#endif

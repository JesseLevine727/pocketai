#include "certified_branch.h"
void pa_startup_branch_test(const double *factors, const double *weights,
    const int32_t *power, const uint32_t *shift, const int32_t *values,
    int32_t *output, int32_t *status, uint32_t count) {
  for (uint32_t i = 0; i < count; ++i) {
    pa_tenth_factor factor = pa_tenth_prepare_factor(factors[i]);
    status[i] = startup_certified_branch(&factor, weights[i],
        (uint32_t)power[i]<<20, shift[i], values[i], output+i);
  }
}

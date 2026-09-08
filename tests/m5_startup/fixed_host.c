#include "fixed_branch.h"
void pa_startup_fixed_test(const int32_t *values, const uint32_t *weight,
    const uint32_t *row, const uint32_t *shift, int32_t *output,
    int32_t *status, uint32_t count) {
  for (uint32_t i = 0; i < count; ++i)
    status[i] = startup_fixed_branch(values[i], weight[i], row[i], shift[i], output+i);
}

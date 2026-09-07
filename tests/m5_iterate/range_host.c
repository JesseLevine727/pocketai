#include <stdint.h>
#include "../../runtime/m5_fast/exact_power2.c.inc"
#include "../../runtime/m5_iterate/project_range.c.inc"
double pa_iter_range_candidate(const int32_t *sums, const double *scales,
                                const double *bias, const int16_t *residual,
                                uint32_t exponent, uint32_t count) {
  uint64_t maximum = 0;
  for (uint32_t i = 0; i < count; ++i)
    maximum = pa_iter_range_max(maximum, pa_iter_range_term(sums[i], scales[i], bias[i],
                                  residual ? residual+i : 0, exponent));
  union { uint64_t bits; double floating; } result = {.bits = maximum};
  return result.floating;
}
double pa_iter_range_reference(const int32_t *sums, const double *scales,
                                const double *bias, const int16_t *residual,
                                uint32_t exponent, uint32_t count) {
  double maximum = 0.0;
  for (uint32_t i = 0; i < count; ++i) {
    double logical = (double)sums[i] * scales[i] + bias[i];
    if (logical < 0) logical = -logical;
    if (residual) {
      double old = (double)residual[i] * (double)(UINT64_C(1) << exponent) / 256.0;
      if (old < 0) old = -old;
      logical += old;
    }
    if (logical > maximum) maximum = logical;
  }
  return maximum;
}

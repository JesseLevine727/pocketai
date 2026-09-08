#ifdef PA_STARTUP_TEST_HIGH
#include "high_product.h"
#elif defined(PA_STARTUP_TEST_IMPLICIT)
#include "implicit_product.h"
#else
#include "interval_product.h"
#endif
void pa_startup_product_test(const double *factors, const double *weights,
    const int32_t *power, const uint32_t *shift, uint32_t *output, uint32_t count) {
  for (uint32_t i = 0; i < count; ++i) {
    pa_tenth_factor factor = pa_tenth_prepare_factor(factors[i]);
    output[i] = pa_startup_project_multiplier(&factor, weights[i],
        (uint32_t)power[i]<<20, shift[i]);
  }
}

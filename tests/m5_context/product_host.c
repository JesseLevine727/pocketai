#include "score_product.h"
uint32_t pa_context_host_score_product(double query, double unit, uint32_t shift) {
  pa_tenth_factor factor = pa_tenth_prepare_factor(query);
  return pa_context_score_product(&factor, unit, shift);
}

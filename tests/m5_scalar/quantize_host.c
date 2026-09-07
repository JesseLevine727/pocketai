#include "quantize.h"
#include "affine_round.h"
int8_t pa_scalar_quantize_probe(int32_t value, uint32_t multiplier) {
  return pa_scalar_quantize24(value, multiplier);
}
int64_t pa_scalar_rne_probe(int32_t value, uint32_t multiplier, uint32_t shift) {
  return pa_scalar_rne_product(value, multiplier, shift);
}
uint32_t pa_scalar_scaled_probe(uint64_t bits, uint32_t shift) {
  return pa_scalar_rne_scaled32(bits, shift);
}

#ifndef PA_M5_TENTH_RECIPROCAL_H
#define PA_M5_TENTH_RECIPROCAL_H
#include <stdint.h>

static inline uint64_t pa_tenth_high_product(uint64_t a, uint64_t b) {
  uint64_t p00 = (uint64_t)(uint32_t)a * (uint32_t)b;
  uint64_t p01 = (uint64_t)(uint32_t)a * (uint32_t)(b >> 32);
  uint64_t p10 = (uint64_t)(uint32_t)(a >> 32) * (uint32_t)b;
  uint64_t p11 = (uint64_t)(uint32_t)(a >> 32) * (uint32_t)(b >> 32);
  uint64_t middle = (p00 >> 32) + (uint64_t)(uint32_t)p01 + (uint32_t)p10;
  return p11 + (p01 >> 32) + (p10 >> 32) + (middle >> 32);
}

/* The Newton estimate only proposes a quotient. Exact full-product/remainder
 * checks correct and certify it before ties-to-even rounding; any estimate
 * outside the bounded correction window falls back to the original divide.
 * There is no approximate result path. */
static inline double pa_tenth_reciprocal(double value) {
  union { double floating; uint64_t bits; } input = {.floating = value}, output;
  uint32_t encoded = (uint32_t)((input.bits >> 52) & 2047u);
  uint64_t fraction = input.bits & UINT64_C(0xfffffffffffff);
  if (!encoded || encoded == 2047) return 1.0 / value;
  if (!fraction) {
    int exponent = 2046-(int)encoded;
    if (exponent <= 0 || exponent >= 2047) return 1.0 / value;
    output.bits = (input.bits & (UINT64_C(1) << 63)) | (uint64_t)exponent << 52;
    return output.floating;
  }
  uint64_t denominator = fraction | (UINT64_C(1) << 52);
  uint64_t normalized = denominator << 11;
  uint32_t seed = (UINT32_C(1) << 31) / ((uint32_t)(normalized >> 48)+1u);
  uint64_t estimate = (uint64_t)seed << 48;
  for (unsigned step = 0; step < 2; ++step) {
    uint64_t high = pa_tenth_high_product(normalized, estimate);
    if (high > (UINT64_C(1) << 63)) return 1.0 / value;
    uint64_t error = (UINT64_C(1) << 63)-high;
    uint64_t correction = pa_tenth_high_product(estimate, error) << 1;
    if (estimate+correction < estimate) return 1.0 / value;
    estimate += correction;
  }
  uint64_t quotient = estimate >> 11;
  uint64_t product_low = quotient * denominator;
  uint64_t product_high = pa_tenth_high_product(quotient, denominator);
  const uint64_t target_high = UINT64_C(1) << 41; /* 2^105 */
  unsigned corrections = 0;
  while (product_high > target_high || (product_high == target_high && product_low)) {
    if (++corrections > 4) return 1.0 / value;
    --quotient;
    product_high -= product_low < denominator;
    product_low -= denominator;
  }
  uint64_t remainder = 0-product_low;
  /* Certify N-product fits the remainder word, then establish remainder<D. */
  if (target_high-product_high != (product_low != 0)) return 1.0 / value;
  while (remainder >= denominator) {
    if (++corrections > 4) return 1.0 / value;
    ++quotient; remainder -= denominator;
  }
  quotient += remainder > denominator-remainder ||
              (remainder == denominator-remainder && (quotient & 1u));
  int exponent = 2045-(int)encoded;
  if (quotient & (UINT64_C(1) << 53)) { quotient >>= 1; ++exponent; }
  if (exponent <= 0 || exponent >= 2047) return 1.0 / value;
  output.bits = (input.bits & (UINT64_C(1) << 63)) | ((uint64_t)exponent << 52) |
                (quotient & UINT64_C(0xfffffffffffff));
  return output.floating;
}
#endif

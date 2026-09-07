#ifndef PA_M5_SCALAR_QUANTIZE_H
#define PA_M5_SCALAR_QUANTIZE_H
#include <stdint.h>

/* Exact signed int32 * uint32 followed by RNE for shift in [0,31]. This is
 * the full int64 result, not saturation. Smooth overflow probes need it. */
static inline int64_t pa_scalar_rne_product(int32_t value, uint32_t multiplier,
                                          uint32_t shift) {
  if (!shift) return (int64_t)value * multiplier;
  uint32_t magnitude = value < 0 ? 0u - (uint32_t)value : (uint32_t)value;
  uint64_t product = (uint64_t)magnitude * multiplier;
  uint64_t quotient = product >> shift;
  uint32_t remainder = (uint32_t)product & ((UINT32_C(1) << shift) - 1u);
  uint32_t half = UINT32_C(1) << (shift - 1u);
  quotient += remainder > half || (remainder == half && (quotient & 1u));
  return value < 0 ? -(int64_t)quotient : (int64_t)quotient;
}

/* Only the proven int16 / nonnegative Q15 probability domain [-32768,32768].
 * Keep the full unsigned product, then one ties-to-even shift and saturation.
 * Neither a truncated multiply nor a second rounding is interchangeable. */
static inline int8_t pa_scalar_quantize24(int32_t value, uint32_t multiplier) {
  uint32_t magnitude = value < 0 ? 0u - (uint32_t)value : (uint32_t)value;
  uint64_t product = (uint64_t)magnitude * multiplier;
  uint32_t quotient = (uint32_t)(product >> 24);
  uint32_t remainder = (uint32_t)product & UINT32_C(0xffffff);
  quotient += remainder > UINT32_C(0x800000) ||
              (remainder == UINT32_C(0x800000) && (quotient & 1u));
  if (value < 0) return quotient >= 128 ? -128 : (int8_t)-(int32_t)quotient;
  return quotient > 127 ? 127 : (int8_t)quotient;
}
#endif

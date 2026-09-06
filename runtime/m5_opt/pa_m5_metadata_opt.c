// Second isolated candidate: reuse the exact integer shift optimization.
#define pa_m5_affine_metadata pa_m5_baseline_affine_metadata
#include "pa_m5_numerics_opt.c"
#undef pa_m5_affine_metadata

// Equivalent to RNE(value * 2^shift), for finite nonnegative binary64 and
// shift in [0,31]. Multiplication by a power of two is exact here; positive
// subnormals remain far below 0.5, and overflow is the existing sentinel.
static uint64_t rne_scaled_bits(uint64_t bits, uint32_t shift) {
  unsigned encoded = (unsigned)((bits >> 52) & 0x7ffu);
  if (!encoded) return 0;
  int exponent = (int)encoded - 1023 + (int)shift;
  uint64_t fraction = bits & UINT64_C(0x000fffffffffffff);
  if (exponent < -1) return 0;
  if (exponent == -1) return fraction ? 1 : 0;
  if (exponent >= 64) return UINT64_MAX;
  uint64_t mantissa = fraction | UINT64_C(0x0010000000000000);
  if (exponent >= 52) return mantissa << (exponent - 52);
  unsigned right = (unsigned)(52 - exponent);
  uint64_t q = mantissa >> right;
  uint64_t remainder = mantissa & ((UINT64_C(1) << right) - 1);
  uint64_t half = UINT64_C(1) << (right - 1);
  return q + (remainder > half || (remainder == half && (q & 1u)));
}

int pa_m5_affine_metadata(const double *scales, uint32_t count,
                          uint32_t *multipliers, uint32_t *shift) {
  if (!scales || !count || !multipliers || !shift) return -1;
  uint64_t maximum = 0;
  for (uint32_t i = 0; i < count; ++i) {
    union { double floating; uint64_t bits; } value = {.floating = scales[i]};
    if (((value.bits >> 52) & 0x7ffu) == 0x7ffu ||
        ((value.bits >> 63) && (value.bits << 1)))
      return pa_m5_baseline_affine_metadata(scales, count, multipliers, shift);
    value.bits &= UINT64_C(0x7fffffffffffffff); // normalize negative zero
    if (value.bits > maximum) maximum = value.bits;
  }
  // For nonnegative finite values, binary64 bit order and rounded scaled
  // value are monotonic. Only the maximum determines the common shift.
  uint32_t selected = 31;
  while (selected && rne_scaled_bits(maximum, selected) >= UINT32_C(0x80000000))
    --selected;
  for (uint32_t i = 0; i < count; ++i) {
    union { double floating; uint64_t bits; } value = {.floating = scales[i]};
    value.bits &= UINT64_C(0x7fffffffffffffff);
    uint64_t rounded = rne_scaled_bits(value.bits, selected);
    if (rounded >= UINT32_C(0x80000000) || (!rounded && value.bits))
      return pa_m5_baseline_affine_metadata(scales, count, multipliers, shift);
    multipliers[i] = (uint32_t)rounded;
  }
  *shift = selected;
  return 0;
}

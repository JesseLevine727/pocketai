// An explicit, isolated derivation; the accepted M5 source remains unchanged.
// Keep the original fallback for arbitrary denominators and error semantics.
#define pa_m5_rne_u64 pa_m5_baseline_rne_u64
#define pa_m5_rne_i64 pa_m5_baseline_rne_i64
#include "../m5/pa_m5_numerics.c"
#undef pa_m5_rne_u64
#undef pa_m5_rne_i64

uint64_t pa_m5_rne_u64(uint64_t numerator, uint64_t denominator) {
  if (!denominator || (denominator & (denominator - 1)))
    return pa_m5_baseline_rne_u64(numerator, denominator);
  // Every activation requantization and smoothing probe divides by 2^shift.
  // RV32 has no 64-bit divide instruction; shift/mask is exactly equivalent.
  if (denominator == 1) return numerator;
  uint32_t low = (uint32_t)denominator;
  unsigned shift = low ? (unsigned)__builtin_ctz(low) :
                        32u + (unsigned)__builtin_ctz((uint32_t)(denominator >> 32));
  uint64_t q = numerator >> shift;
  uint64_t remainder = numerator & (denominator - 1), half = denominator >> 1;
  return q + (remainder > half || (remainder == half && (q & 1u)));
}

int64_t pa_m5_rne_i64(int64_t numerator, uint64_t denominator) {
  if (!denominator || numerator == INT64_MIN) return INT64_MIN;
  uint64_t magnitude = numerator < 0 ? (uint64_t)-numerator : (uint64_t)numerator;
  uint64_t rounded = pa_m5_rne_u64(magnitude, denominator);
  if (rounded > INT64_MAX) return INT64_MIN;
  return numerator < 0 ? -(int64_t)rounded : (int64_t)rounded;
}

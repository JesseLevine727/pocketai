#ifndef PA_M5_STARTUP_HIGH_PRODUCT_H
#define PA_M5_STARTUP_HIGH_PRODUCT_H
#include "mul_factor.h"
#include "affine_round.h"
static inline uint32_t startup_high_rne(uint64_t value, uint32_t right) {
  uint64_t q = value>>right;
  uint64_t remainder = value&((UINT64_C(1)<<right)-1);
  uint64_t half = UINT64_C(1)<<(right-1);
  q += remainder > half || (remainder == half && (q&1u));
  return q >= UINT32_C(0x80000000) ? UINT32_C(0x80000000) : (uint32_t)q;
}

#ifdef PA_STARTUP_SHARED_PRODUCT
static __attribute__((noinline))
#else
static inline
#endif
uint32_t pa_startup_project_multiplier(const pa_tenth_factor *factor,
    double weight, uint32_t adjustment, uint32_t shift) {
  union { double floating; uint64_t bits; } w = {.floating = weight};
  uint32_t high = (uint32_t)(w.bits>>32), encoded = (high>>20)&2047u;
  int sum = (int)factor->exponent+(int)encoded;
  int power = (int32_t)adjustment>>20;
  int right = 2150-sum-power-(int)shift;
  if (!(high>>31) && !factor->sign && encoded && encoded < 2047 &&
      factor->exponent && factor->exponent < 2047 && sum > 1023 && sum < 3068 &&
      right > 64 && right < 128) {
    uint32_t low = (uint32_t)w.bits;
    high = (high&0xfffffu)|0x100000u;
    uint64_t p01 = (uint64_t)factor->low*high;
    uint64_t p10 = (uint64_t)factor->high*low;
    uint64_t p11 = (uint64_t)factor->high*high;
    uint64_t lo = (p01<<32)+(p10<<32);
    uint64_t hi = p11+(p01>>32)+(p10>>32)+(lo < (p01<<32));
    /* Omitted low*low is unsigned and <2^64, hence adds at most one to hi.
     * The exact 106-bit product lies in [hi, hi+2) high-word units. Its
     * binary64 rounding changes it by less than one further high-word unit.
     * The deliberately wider [hi-1, hi+3] encloses BOTH rounding boundaries.
     * Equal endpoint integer results therefore certify the exact multiplier. */
    uint32_t r = (uint32_t)right-64;
    uint32_t lower = startup_high_rne(hi-1, r), upper = startup_high_rne(hi+3, r);
    if (lower == upper) return lower;
  }
  w.floating = pa_tenth_mul_factor(factor, weight);
  w.bits += (uint64_t)adjustment<<32;
  return pa_scalar_rne_scaled32(w.bits, shift);
}
#endif

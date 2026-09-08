#ifndef PA_M5_STARTUP_INTERVAL_PRODUCT_H
#define PA_M5_STARTUP_INTERVAL_PRODUCT_H
#include "mul_factor.h"
#include "affine_round.h"

/* RNE of a positive 64-bit integer / 2^right, for 32<=right<=63. */
static inline uint32_t startup_rne_upper(uint64_t product, uint32_t right) {
  uint32_t high = (uint32_t)(product>>32), low = (uint32_t)product;
  uint32_t r = right-32;
  if (!r) return high+(low > UINT32_C(0x80000000) ||
      (low == UINT32_C(0x80000000) && (high&1u)));
  uint32_t q = high>>r, rem = high&((UINT32_C(1)<<r)-1);
  uint32_t half = UINT32_C(1)<<(r-1);
  return q+(rem > half || (rem == half && (low || (q&1u))));
}

/* Exact two-rounding product-to-integer. A coarse enclosure only decides
 * when BOTH endpoints round to the SAME integer; it never supplies an
 * approximate multiplier. Otherwise retain the complete 106-bit product.
 * A,B are top-32 significands. The exact product in these units is in
 * [A*B, A*B+A+B+1]. Binary64 rounding changes it by at most 1024 units;
 * expand by 2048 for a simple conservative inclusive bound. */
#ifdef PA_STARTUP_SHARED_PRODUCT
static __attribute__((noinline))
#else
static inline
#endif
uint32_t pa_startup_project_multiplier(const pa_tenth_factor *factor,
    double weight, uint32_t adjustment, uint32_t shift) {
  union { double floating; uint64_t bits; } w = {.floating = weight};
  uint32_t whigh = (uint32_t)(w.bits>>32), encoded = (whigh>>20)&2047u;
  int sum = (int)factor->exponent+(int)encoded;
  int power = (int32_t)adjustment >> 20;
  int right = 2108-sum-power-(int)shift;
  if (!(whigh>>31) && !factor->sign && encoded && encoded < 2047 &&
      factor->exponent && factor->exponent < 2047 && sum > 1023 && sum < 3068 &&
      right >= 33 && right <= 63) {
    uint32_t a = (factor->high<<11)|(factor->low>>21);
    uint32_t b = ((whigh&0xfffffu)<<11)|UINT32_C(0x80000000)|((uint32_t)w.bits>>21);
    uint64_t product = (uint64_t)a*b;
    uint64_t extra = (uint64_t)a+b+2049u;
    if (product <= UINT64_MAX-extra) {
      uint32_t lower = startup_rne_upper(product-2048u, (uint32_t)right);
      uint32_t upper = startup_rne_upper(product+extra, (uint32_t)right);
      if (lower == upper) return lower;
    }
  }
  w.floating = pa_tenth_mul_factor(factor, weight);
  w.bits += (uint64_t)adjustment<<32;
  return pa_scalar_rne_scaled32(w.bits, shift);
}
#endif

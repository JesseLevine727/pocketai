#ifndef PA_CONTEXT_SCORE_PRODUCT_H
#define PA_CONTEXT_SCORE_PRODUCT_H
#include "mul_factor.h"

/* RNE(RNE_binary64(query*unit) * 2^(5+shift)), exactly. The first rounding
 * is retained in the full 106-bit product BEFORE integer rounding. Never
 * replace the two roundings with one; near-halfway values distinguish them. */
static inline uint32_t pa_context_score_product(const pa_tenth_factor *factor,
                                                 double unit, uint32_t shift) {
  union { double floating; uint64_t bits; } x = {.floating = unit};
  uint32_t encoded = (uint32_t)((x.bits >> 52) & 2047u);
  int sum = (int)factor->exponent + (int)encoded;
  int right = 2145-sum-(int)shift;
  if ((x.bits >> 63) || factor->sign || !encoded || encoded == 2047 ||
      !factor->exponent || factor->exponent == 2047 ||
      sum <= 1023 || sum >= 3068 || right <= 64 || right >= 128)
    return UINT32_MAX;
  uint32_t low = (uint32_t)x.bits;
  uint32_t high = (uint32_t)((x.bits >> 32) & 0xfffffu) | 0x100000u;
  uint64_t p00 = (uint64_t)factor->low*low;
  uint64_t p01 = (uint64_t)factor->low*high;
  uint64_t p10 = (uint64_t)factor->high*low;
  uint64_t p11 = (uint64_t)factor->high*high;
  uint64_t lo0 = p00+(p01 << 32), lo = lo0+(p10 << 32);
  uint64_t hi = p11+(p01 >> 32)+(p10 >> 32)+(lo0 < p00)+(lo < lo0);
  uint32_t discard = 52u+(uint32_t)(hi >> 41);
  uint64_t mask = (UINT64_C(1) << discard)-1;
  uint64_t increment = (UINT64_C(1) << (discard-1))-1+((lo >> discard) & 1u);
  uint64_t rounded = lo+increment;
  hi += rounded < lo; lo = rounded & ~mask;
  uint32_t high_right = (uint32_t)right-64;
  uint64_t quotient = hi >> high_right;
  uint64_t remainder = hi & ((UINT64_C(1) << high_right)-1);
  uint64_t half = UINT64_C(1) << (high_right-1);
  quotient += remainder > half || (remainder == half && (lo || (quotient & 1u)));
  return quotient >= UINT32_C(0x80000000) ? UINT32_C(0x80000000) : (uint32_t)quotient;
}
#endif

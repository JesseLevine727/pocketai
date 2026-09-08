#ifndef PA_M5_STARTUP_CERTIFIED_BRANCH_H
#define PA_M5_STARTUP_CERTIFIED_BRANCH_H
#include "mul_factor.h"
#include "word_affine.h"
/* Certify the FINAL integer branch, not the intermediate multiplier. The
 * top-21 significands enclose the exact rounded binary64 product. Enclosing
 * multiplier rounding and then BOTH signed-product endpoints proves equality
 * to the original two-rounding computation. No approximate output is used. */
static __attribute__((noinline, unused)) int startup_certified_branch(
    const pa_tenth_factor *factor, double weight, uint32_t adjustment,
    uint32_t shift, int32_t value, int32_t *output) {
  union { double floating; uint64_t bits; } w = {.floating = weight};
  uint32_t high = (uint32_t)(w.bits>>32), exponent = (high>>20)&2047u;
  int sum = (int)factor->exponent+(int)exponent;
  int right = 2086-sum-((int32_t)adjustment>>20)-(int)shift;
  if ((high>>31) || factor->sign || !exponent || exponent == 2047 ||
      !factor->exponent || factor->exponent == 2047 || sum <= 1023 || sum >= 3068 ||
      right < 12 || right > 31 || !shift || shift > 31) return 0;
  uint32_t a = factor->high, b = (high&0xfffffu)|0x100000u;
  uint64_t product = (uint64_t)a*b;
  /* Omitted significands contribute < A+B+1 units. Binary64 rounding
   * contributes <1 unit here. Floor/ceil also enclose multiplier RNE. */
  uint64_t lower = product-1, upper = product+a+b+2;
  uint32_t r = (uint32_t)right;
  uint32_t low = (uint32_t)lower, hi = (uint32_t)(lower>>32);
  uint32_t upper_low = (uint32_t)upper, upper_hi = (uint32_t)(upper>>32);
  if ((hi>>r) || (upper_hi>>r)) return 0;
  uint32_t m0 = (low>>r)|(hi<<(32-r));
  uint32_t m1 = ((upper_low>>r)|(upper_hi<<(32-r)))+
      ((upper_low&((UINT32_C(1)<<r)-1)) != 0);
  if (!m0 || m1 >= UINT32_C(0x80000000)) return 0;
  uint32_t magnitude = value < 0 ? 0u-(uint32_t)value : (uint32_t)value;
  int32_t q0, q1;
  if (!startup_word_affine(value, magnitude, m0, shift, &q0) ||
      !startup_word_affine(value, magnitude, m1, shift, &q1) || q0 != q1) return 0;
  *output = q0; return 1;
}
#endif

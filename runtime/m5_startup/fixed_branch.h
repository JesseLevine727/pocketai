#ifndef PA_M5_STARTUP_FIXED_BRANCH_H
#define PA_M5_STARTUP_FIXED_BRANCH_H
#include <stdint.h>
/* W=RNE(weight*2^S), R=RNE(unit*2^(power+shift-S+30)), both <2^31.
 * M'=RNE(W*R/2^30) differs from the original ordered-binary64 multiplier M
 * by at most FOUR integer units: input roundings contribute <2+epsilon,
 * output roundings <1+epsilon. The original product is normal and <2^31.
 * Accept only when that entire interval produces the same final signed RNE.
 * Otherwise the caller computes the exact original multiplier and product. */
static __attribute__((noinline, unused)) int startup_fixed_branch(int32_t value,
    uint32_t weight, uint32_t row, uint32_t shift, int32_t *output) {
  if (weight >= UINT32_C(0x80000000) || row >= UINT32_C(0x80000000) ||
      !shift || shift > 31) return 0;
  uint64_t product = (uint64_t)weight*row;
  uint32_t lo = (uint32_t)product, hi = (uint32_t)(product>>32);
  uint32_t multiplier = (lo>>30)|(hi<<2), rem = lo&0x3fffffffu;
  multiplier += rem > 0x20000000u || (rem == 0x20000000u && (multiplier&1u));
  if (multiplier <= 4 || multiplier >= UINT32_C(0x7ffffffb)) return 0;
  uint32_t magnitude = value < 0 ? 0u-(uint32_t)value : (uint32_t)value;
  if (magnitude > (UINT32_C(1)<<26)) return 0;
  uint32_t error = magnitude<<2, half = UINT32_C(1)<<(shift-1);
  if (error >= half) return 0;
  product = (uint64_t)magnitude*multiplier;
  lo = (uint32_t)product; hi = (uint32_t)(product>>32);
  if (hi>>shift) return 0;
  uint32_t q = (lo>>shift)|(hi<<(32-shift));
  rem = lo&((UINT32_C(1)<<shift)-1);
  if (rem < half) { if (rem+error >= half) return 0; }
  else { if (rem <= half+error) return 0; ++q; }
  if (q >= (UINT32_C(1)<<29)) return 0;
  *output = value < 0 ? -(int32_t)q : (int32_t)q;
  return 1;
}
#endif
